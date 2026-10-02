# Job Scanner

Daily UK job scan. Fetches listings, screens them against hard rules
(sponsorship, Sept 2027 finish, 0 to 2 years, no clearance), scores fit,
and emails a morning digest. Built so the judge can be swapped to
TypeSafe AI's Jev with one config line.

## How a run flows

```
sources/ ──► store (new only) ──► enrich (drop snippet dupes) ──► prefilter (cheap rules)
                                                                        │
digest ◄── route (Strong / Check / Drop) ◄── judge (heuristic or Jev) ◄─┤
   │                                                                     │
notify (email) ──► store.record                          sponsors (Home Office register)
```

Searching is plain code (same sources every run, counts shown per source).
Only the judging is AI. That split is what stops coverage from drifting.

## Repo map

| Path | What it does |
|---|---|
| `jobscan/main.py` | Runs the pipeline once, start to finish. `--dry-run`, `--only <source>`, `--limit N`. |
| `jobscan/models.py` | All data types. `RawJob` (input), `Gates`/`Fit`/`Flags`/`JobVerdict` (the Jev schema), `RoutedJob` (output). Field descriptions are the questions sent to the judge. |
| **Sources** | |
| `jobscan/sources/base.py` | `Source` interface, HTTP helper, HTML-to-text. |
| `jobscan/sources/ats.py` | Greenhouse, Lever, Ashby public APIs. Full descriptions, no keys. |
| `jobscan/sources/boards.py` | Adzuna and Reed (free keys), SimplifyJobs new-grad list (no key). |
| `jobscan/sources/gmail_alerts.py` | Reads LinkedIn / Indeed / other alert emails from your `job-alerts` Gmail label. |
| `jobscan/parsers/linkedin.py` | Pulls jobs out of LinkedIn alert emails (`/jobs/view/<id>` links). |
| `jobscan/parsers/indeed.py` | Pulls jobs out of Indeed alert emails (`jk=<id>` links). |
| `jobscan/parsers/generic.py` | Fallback for any other alert sender. |
| `jobscan/parsers/common.py` | Shared parsing helpers. |
| **Filtering** | |
| `jobscan/store.py` | SQLite of every job already seen (`data/jobs.db`). Each job is judged once. |
| `jobscan/enrich.py` | Drops snippet-only copies when the full ATS version is also present. |
| `jobscan/prefilter.py` | Free rule drops: not UK, senior titles, internships, salary under £33,400. |
| `jobscan/sponsors.py` | Downloads the Home Office sponsor register daily, matches company names. |
| **Judge** | |
| `jobscan/judge/base.py` | `Judge` interface + parallel `judge_many`. Errors go to Check manually. |
| `jobscan/judge/heuristic.py` | Free keyword judge. Runs today, and is the baseline to compare Jev against. |
| `jobscan/judge/jev.py` | Jev adapter. Builds questions from `models.py`. Only `_call()` is left, to fill from Jev docs. |
| **Output** | |
| `jobscan/route.py` | Probabilities to buckets using `settings.yaml` thresholds. Ranks by role order. |
| `jobscan/digest.py` | Builds the HTML email: counts, Strong, Check manually, drops by reason, coverage per source. |
| `jobscan/notify.py` | Sends the email via Gmail SMTP (app password). |
| **Config** | |
| `config/settings.yaml` | Every tunable number: judge choice, salary floor, gate thresholds, role ranking, search terms. |
| `config/profile.yaml` | Short candidate profile sent to the judge with every job. |
| `config/companies.yaml` | Company ATS slugs to fetch directly. Starting list is unverified. |
| **Ops** | |
| `.github/workflows/daily.yml` | Runs every day at 06:00 UTC, emails you, commits `data/jobs.db` back. |
| `scripts/check_companies.py` | Tests every slug in `companies.yaml`, lists broken ones. |
| `scripts/gmail_auth.py` | One-time Gmail OAuth, prints the refresh token for GitHub Secrets. |
| `tests/test_pipeline.py` | Prefilter, routing, enrich, parsers, Jev question building. |
| `.env.example` | Every secret name, for local runs. |

## Buckets

- **Strong**: all gates pass, sponsor confirmed (register or posting), match 4/5+, full description.
- **Check manually**: gates pass but something is unclear (sponsorship, snippet only, judge error).
- **Drop**: a gate failed. Counted by reason at the bottom of the email, for tuning.

## Setup

1. `pip install -r requirements.txt`
2. `python -m pytest -q`
3. `python -m jobscan.main --dry-run` then open `out/digest.html`.
4. `python scripts/check_companies.py`, fix or remove broken slugs.
5. Push to a **private** GitHub repo.
6. Add Secrets (Settings > Secrets and variables > Actions): `SMTP_USER`, `SMTP_PASS`, `DIGEST_TO`.
   Optional: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `REED_API_KEY`, Gmail trio, `JEV_API_KEY`.
7. Actions tab > daily-job-scan > Run workflow, to test once.

## LinkedIn / Indeed

1. Set daily job alerts on both sites (UK, entry level, one per role family).
2. Gmail filter on the alert senders, apply label `job-alerts`.
3. `python scripts/gmail_auth.py`, add the three `GMAIL_*` secrets.
4. Save one real alert email per site to `tests/fixtures/` and check the parsers against it.

## Switching to Jev

1. Fill in `JevJudge._call()` in `jobscan/judge/jev.py` from the Jev docs.
2. Add `JEV_API_KEY` secret.
3. `judge: jev` in `config/settings.yaml`.
4. Optional: run both judges on the same jobs and compare buckets.
