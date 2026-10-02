"""Runs the whole pipeline once.

    python -m jobscan.main              # full run: fetch, judge, email, save state
    python -m jobscan.main --dry-run    # no email, no state saved, digest -> out/digest.html
    python -m jobscan.main --only simplify_newgrad --dry-run
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from jobscan import db, digest, notify, prefilter
from jobscan.enrich import enrich
from jobscan.judge import make_judge
from jobscan.models import Bucket, RoutedJob
from jobscan.route import route
from jobscan.sources.ats import Ashby, Greenhouse, Lever
from jobscan.sources.base import Source
from jobscan.sources.boards import Adzuna, Reed, SimplifyNewGrad
from jobscan.sponsors import SponsorRegister
from jobscan.store import Store

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """Local runs: read .env if present. GitHub Actions uses Secrets instead."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / "config" / name).read_text())


def build_sources(settings: dict, companies: dict) -> list[Source]:
    on = settings.get("sources", {})
    srcs: list[Source] = []
    if on.get("gmail_alerts", True) and os.environ.get("GMAIL_REFRESH_TOKEN"):
        from jobscan.sources.gmail_alerts import GmailAlerts
        srcs.append(GmailAlerts(settings["alert_senders"]))
    if on.get("ats", True):
        srcs += [Greenhouse(s) for s in companies.get("greenhouse") or []]
        srcs += [Lever(s) for s in companies.get("lever") or []]
        srcs += [Ashby(s) for s in companies.get("ashby") or []]
    if on.get("simplify_newgrad"):
        srcs.append(SimplifyNewGrad())
    if on.get("adzuna") and os.environ.get("ADZUNA_APP_ID"):
        srcs.append(Adzuna(settings["search_terms"]))
    if on.get("reed") and os.environ.get("REED_API_KEY"):
        srcs.append(Reed(settings["search_terms"]))
    return srcs


def alert_coverage(settings: dict, sources: list[Source], jobs: list) -> list[dict]:
    """One coverage row per alert board, so a board that sent nothing is visible."""
    senders = settings.get("alert_senders", [])
    gmail = next((s for s in sources if s.name == "gmail_alerts"), None)
    if gmail is None:
        if not settings.get("sources", {}).get("gmail_alerts", True):
            return []
        return [{"source": f"{s['name']} (alert)", "tier": s["tier"], "fetched": 0,
                 "error": "Gmail not connected yet (run scripts/gmail_auth.py)"} for s in senders]
    rows = []
    for s in senders:
        n_jobs = sum(1 for j in jobs if j.source == f"{s['name']}_alert")
        rows.append({"source": f"{s['name']} (alert)", "tier": s["tier"], "fetched": n_jobs,
                     "emails": gmail.emails_by_sender.get(s["name"], 0)})
    if gmail.emails_by_sender.get("unmatched"):
        rows.append({"source": "unmatched senders (alert)", "tier": "extra",
                     "fetched": sum(1 for j in jobs if j.source.startswith("alert:")),
                     "emails": gmail.emails_by_sender["unmatched"]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="run a single source by name")
    ap.add_argument("--limit", type=int, help="cap jobs sent to the judge (testing)")
    ap.add_argument("--rejudge", action="store_true",
                    help="ignore the seen-jobs list and re-score everything currently listed")
    args = ap.parse_args()
    load_dotenv()

    settings = load("settings.yaml")
    companies = load("companies.yaml")
    profile = load("profile.yaml")["profile"]

    # 1. Fetch (each source isolated; failures show in the digest)
    sources = build_sources(settings, companies)
    if args.only:
        sources = [s for s in sources if s.name == args.only]
    jobs, coverage = [], []
    for src in sources:
        got = []
        try:
            got = src.fetch()
            jobs += got
            if src.name != "gmail_alerts":  # alert boards get their own rows below
                coverage.append({"source": src.name, "tier": "extra", "fetched": len(got)})
        except Exception as e:  # noqa: BLE001
            coverage.append({"source": src.name, "tier": "main" if src.name == "gmail_alerts" else "extra",
                             "fetched": 0, "error": f"{type(e).__name__}: {e}"[:160]})
        print(f"[fetch] {src.name}: {len(got)} jobs")
    if not args.only:
        coverage = alert_coverage(settings, sources, jobs) + coverage

    # 2. Dedupe against history + within run
    store = Store(ROOT / "data" / "jobs.db")
    fetched = len(jobs)
    jobs = store.filter_new(jobs, ignore_history=args.rejudge)
    new = len(jobs)

    # 3. Drop snippet copies of jobs we have in full
    jobs, dupes = enrich(jobs)

    # 4. Cheap rules
    floor = settings["salary"]["new_entrant_floor_gbp"]
    pre_dropped: list[RoutedJob] = []
    kept = []
    for j in jobs:
        reason = prefilter.check(j, floor)
        if reason:
            pre_dropped.append(RoutedJob(job=j, bucket=Bucket.drop, reasons=[reason]))
        else:
            kept.append(j)
    if args.limit:
        kept = kept[: args.limit]
    print(f"[filter] fetched={fetched} new={new} dupes={dupes} to_judge={len(kept)}")

    # 5. Sponsor register
    try:
        register = SponsorRegister()
    except Exception as e:  # noqa: BLE001
        print(f"[sponsors] unavailable: {e}")
        register = SponsorRegister(refresh=False)
    coverage.append({"source": "sponsor_register", "fetched": len(register.names)})

    # 6. Judge + route
    judge = make_judge(settings["judge"], profile)
    verdicts = judge.judge_many(kept)
    routed = [route(j, v, register.is_sponsor(j.company), settings) for j, v in zip(kept, verdicts)]
    routed += pre_dropped  # recorded too, so they are never re-checked

    # 7. Save to Supabase (the dashboard reads from here).
    # Prefilter drops are skipped: they were never judged, so they are just noise.
    stats = {"fetched": fetched, "new": new, "dupes": dupes, "judge": settings["judge"]}
    db_error = None
    if not args.dry_run and db.db_url():
        try:
            added = db.save([r for r in routed if r.verdict is not None])
            db.mark_dropped([r for r in routed if r.verdict is None])
            print(f"[db] {added} jobs added to Supabase")
        except Exception as e:  # noqa: BLE001
            db_error = f"{type(e).__name__}: {e}"[:200]
            print(f"[db] FAILED: {db_error}")
    stats["db_error"] = db_error

    # 8. Digest: full report always saved; email is a short nudge when a dashboard exists
    subject, full_html = digest.build(routed, coverage, stats, settings.get("manual_check"))
    subject = f'{settings["email"]["subject_prefix"]} {subject}'
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    (out / "digest.html").write_text(full_html, encoding="utf-8")
    dash = settings["email"].get("dashboard_url") or ""
    email_html = digest.build_nudge(routed, coverage, stats, dash) if dash else full_html
    (out / "email.html").write_text(email_html, encoding="utf-8")
    print(f"[digest] {subject} -> out/digest.html, out/email.html")

    if args.dry_run:
        return
    notify.send(subject, email_html)
    if db_error:
        # Leave jobs unrecorded so tomorrow's run retries the Supabase insert.
        print("[done] emailed; NOT marking jobs as seen because the database save failed")
        raise SystemExit(1)
    store.record(routed)  # only after the email went out
    print("[done] emailed and saved")


if __name__ == "__main__":
    main()
