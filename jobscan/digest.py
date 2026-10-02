"""Builds the morning email (HTML). Order: counts, coverage per source,
Strong, Check manually, dropped-by-reason (for tuning)."""
from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape

from jobscan.models import Bucket, RoutedJob

CSS = """
body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1d1d1f;max-width:760px;margin:auto;padding:16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}
.sub{color:#666;font-size:13px} table{border-collapse:collapse;width:100%;font-size:13px}
td,th{text-align:left;padding:4px 8px;border-bottom:1px solid #eee} .err{color:#b00020;font-weight:600}
.job{padding:8px 0;border-bottom:1px solid #eee} .job a{font-weight:600;color:#0a58ca;text-decoration:none}
.meta{color:#555;font-size:13px} .why{font-size:12px;color:#333;margin-top:2px}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:8px;background:#eef;margin-right:4px}
.pm{background:#fde9c8}
"""


def _job_html(r: RoutedJob) -> str:
    j = r.job
    sal = ""
    if j.salary_min or j.salary_max:
        sal = f" · £{(j.salary_min or j.salary_max):,}" + (
            f" to £{j.salary_max:,}" if j.salary_max and j.salary_min and j.salary_max != j.salary_min else "")
    fam = r.verdict.fit.role_family.value if r.verdict else "unknown"
    tag_cls = "tag pm" if fam == "product_management" else "tag"
    return (f'<div class="job"><span class="{tag_cls}">{escape(fam)}</span>'
            f'<a href="{escape(j.url)}">{escape(j.title)}</a>'
            f'<div class="meta">{escape(j.company)} · {escape(j.location or "location not given")}{sal}'
            f' · via {escape(j.source)}</div>'
            f'<div class="why">{escape("; ".join(r.reasons))}</div></div>')


def _cov_row(c: dict) -> str:
    tier = c.get("tier", "")
    name = f"<b>{escape(c['source'])}</b>" if tier == "main" else escape(c["source"])
    emails = c.get("emails", "")
    if c.get("error"):
        status = f'<td colspan="2" class="err">{escape(c["error"])}</td>'
    else:
        warn = ("<span class=err>0 from a main board, check its alert</span>"
                if c["fetched"] == 0 and tier == "main" else "")
        status = f"<td>{c['fetched']}</td><td>{warn}</td>"
    return f"<tr><td>{name}</td><td>{emails}</td>{status}</tr>"


def build(routed: list[RoutedJob], coverage: list[dict], stats: dict,
          manual_check: list[dict] | None = None) -> tuple[str, str]:
    """Returns (subject, html)."""
    strong = sorted([r for r in routed if r.bucket == Bucket.strong], key=lambda r: -r.rank_score)
    check = sorted([r for r in routed if r.bucket == Bucket.check], key=lambda r: -r.rank_score)
    drop_reasons = Counter(reason for r in routed if r.bucket == Bucket.drop for reason in r.reasons)
    n_drop = sum(1 for r in routed if r.bucket == Bucket.drop)

    subject = f"{date.today():%a %d %b}: {len(strong)} strong, {len(check)} to check"

    cov_rows = "".join(_cov_row(c) for c in coverage)
    manual_html = "".join(
        f'<li><a href="{escape(m["url"])}">{escape(m["name"])}</a> · {escape(m.get("note", ""))}</li>'
        for m in (manual_check or []))

    parts = [
        f"<style>{CSS}</style>",
        f"<h1>Job Scanner · {date.today():%A %d %B %Y}</h1>",
        f'<div class="sub">Fetched {stats["fetched"]} · new {stats["new"]} · '
        f'snippet duplicates {stats.get("dupes", 0)} · strong {len(strong)} · '
        f'check {len(check)} · dropped {n_drop} · judge: {escape(stats["judge"])}</div>',
        f"<h2>Strong ({len(strong)})</h2>",
        "".join(_job_html(r) for r in strong) or "<p class=sub>None today.</p>",
        f"<h2>Check manually ({len(check)})</h2>",
        "".join(_job_html(r) for r in check) or "<p class=sub>None today.</p>",
        (f"<h2>Check by hand</h2><ul>{manual_html}</ul>" if manual_html else ""),
        "<h2>Dropped by reason</h2><table>",
        "".join(f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in drop_reasons.most_common()),
        "</table>",
        "<h2>Coverage by source</h2><div class=sub>Bold = main boards.</div>"
        "<table><tr><th>Source</th><th>Emails</th><th>Jobs</th><th></th></tr>",
        cov_rows, "</table>",
    ]
    return subject, "\n".join(parts)
