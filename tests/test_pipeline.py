"""Core logic tests. Run: pytest -q"""
from pathlib import Path

import yaml

from jobscan import prefilter
from jobscan.enrich import enrich
from jobscan.judge.heuristic import HeuristicJudge
from jobscan.judge.jev import QUESTIONS
from jobscan.models import Bucket, RawJob
from jobscan.parsers import indeed, linkedin
from jobscan.route import route
from jobscan.sponsors import normalise

CFG = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())
FLOOR = CFG["salary"]["new_entrant_floor_gbp"]
JUDGE = HeuristicJudge("test profile")


def job(**kw) -> RawJob:
    base = dict(source="test", company="Acme", title="Graduate Software Engineer",
                url="https://x.com/1", location="London, UK")
    base.update(kw)
    return RawJob(**base)


# ---- prefilter ----
def test_prefilter_drops_non_uk():
    assert prefilter.check(job(location="New York, NY"), FLOOR) == "prefilter: not UK"

def test_prefilter_us_namesakes():
    assert prefilter.check(job(location="Cambridge, MA"), FLOOR) == "prefilter: not UK"
    assert prefilter.check(job(location="Cambridge, UK"), FLOOR) is None
    assert prefilter.check(job(location="London, UK; New York, NY"), FLOOR) is None
    assert prefilter.check(job(location="Belfast, Northern Ireland"), FLOOR) is None

def test_prefilter_keeps_empty_location():
    assert prefilter.check(job(location=""), FLOOR) is None

def test_prefilter_drops_senior():
    assert prefilter.check(job(title="Senior Software Engineer"), FLOOR)

def test_prefilter_keeps_associate_pm():
    assert prefilter.check(job(title="Associate Product Manager"), FLOOR) is None

def test_prefilter_salary_floor():
    assert prefilter.check(job(salary_max=28000), FLOOR)
    assert prefilter.check(job(salary_max=45000), FLOOR) is None


# ---- routing via heuristic judge ----
def run(j, on_register=False):
    return route(j, JUDGE.judge(j), on_register, CFG)

def test_strong_when_sponsor_and_good_match():
    j = job(description="Graduate role, 2027 start. Python, machine learning. Visa sponsorship available.")
    assert run(j).bucket == Bucket.strong

def test_drop_on_right_to_work():
    j = job(description="Graduate role. Applicants must have the right to work in the UK.")
    r = run(j)
    assert r.bucket == Bucket.drop and "no sponsorship" in r.reasons[0]

def test_drop_on_clearance():
    assert run(job(description="Graduate role. Must hold SC clearance.")).bucket == Bucket.drop

def test_drop_on_experience():
    assert run(job(description="You will have 5+ years of experience.")).bucket == Bucket.drop

def test_register_makes_strong():
    j = job(description="Graduate role 2027, Python and machine learning.")
    assert run(j, on_register=False).bucket == Bucket.check
    assert run(j, on_register=True).bucket == Bucket.strong

def test_light_data_never_strong():
    j = job(description="Graduate 2027 Python ML visa sponsorship available", light_data=True)
    assert run(j, on_register=True).bucket == Bucket.check

def test_judge_error_goes_to_check():
    assert route(job(), RuntimeError("x"), False, CFG).bucket == Bucket.check

def test_pm_role_detected():
    v = JUDGE.judge(job(title="Associate Product Manager"))
    assert v.fit.role_family.value == "product_management"


# ---- misc ----
def test_enrich_drops_snippet_duplicate():
    full = job(url="https://ats/1", description="full text")
    snip = job(url="https://linkedin/1", light_data=True, company="Acme Ltd")
    out, n = enrich([full, snip])
    assert n == 1 and out == [full]

def test_sponsor_normalise():
    assert normalise("Monzo Bank Limited") == normalise("monzo bank ltd") == "monzo bank"

def test_jev_questions_built_from_schema():
    ids = {q["id"] for q in QUESTIONS}
    assert "gates.offers_sponsorship" in ids and "fit.role_family" in ids
    assert all(q["question"] for q in QUESTIONS)

def test_job_id_ignores_query_string():
    assert job(url="https://a.com/j/1?utm=x").id == job(url="https://a.com/j/1").id


# ---- alert sender routing ----
from jobscan.sources.gmail_alerts import match_sender, parse_email  # noqa: E402

SENDERS = CFG["alert_senders"]

def test_core_boards_configured():
    names = {s["name"] for s in SENDERS if s["tier"] == "main"}
    assert names == {"linkedin", "indeed", "student_circus", "milkround", "bristol_mycareer"}

def test_sender_matching():
    assert match_sender("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", SENDERS)["name"] == "linkedin"
    assert match_sender("Milkround <alerts@milkround.com>", SENDERS)["name"] == "milkround"
    assert match_sender("someone@random.org", SENDERS) is None

def test_alert_jobs_tagged_with_board():
    html = '<div><a href="https://www.milkround.com/job/graduate-developer/acme-job123">Graduate Developer</a>' \
           '<p>Acme</p><p>Bristol</p></div>'
    [j] = parse_email(html, "Milkround <alerts@milkround.com>", SENDERS)
    assert j.source == "milkround_alert" and j.title == "Graduate Developer"


# ---- parsers (synthetic HTML; re-check against a real alert email) ----
def test_linkedin_parser():
    html = """<table><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=x">Graduate ML Engineer</a>
      <p>Monzo · London, England, United Kingdom</p><p>Actively recruiting</p></td></tr></table>"""
    [j] = linkedin.parse(html)
    assert j.url == "https://www.linkedin.com/jobs/view/4012345678/"
    assert j.company == "Monzo" and "London" in j.location

def test_indeed_parser():
    html = """<div><a href="https://uk.indeed.com/rc/clk?jk=abc123def4567890&from=ja">Junior Data Scientist</a>
      <div>Acme Analytics - Bristol</div><div>£35,000 a year</div></div>"""
    [j] = indeed.parse(html)
    assert "jk=abc123def4567890" in j.url and j.company == "Acme Analytics"


# ---- Supabase/Postgres layer (runs only when TEST_DB_URL points at a scratch database) ----
import os  # noqa: E402

import pytest  # noqa: E402

from jobscan import db  # noqa: E402


@pytest.mark.skipif(not os.environ.get("TEST_DB_URL"), reason="set TEST_DB_URL to a scratch Postgres")
def test_db_save_never_overwrites_status():
    url = os.environ["TEST_DB_URL"]
    with db.connect(url) as c:
        db.init(c)
        c.execute("DELETE FROM jobs WHERE id LIKE 'test%'")
    j = job(url="https://test.example/1", description="Graduate 2027 Python ML visa sponsorship available.")
    r = route(j, JUDGE.judge(j), True, CFG)
    assert db.save([r], url) == 1
    assert db.save([r], url) == 0
    with db.connect(url) as c:
        db.update(c, j.id, "applied", "sent")
    db.save([r], url)
    with db.connect(url) as c:
        row = c.execute("SELECT status, notes FROM jobs WHERE id=%s", (j.id,)).fetchone()
        c.execute("DELETE FROM jobs WHERE id=%s", (j.id,))
    assert row == {"status": "applied", "notes": "sent"}


def test_db_rejects_unknown_status():
    with pytest.raises(ValueError):
        db.update(None, "x", "maybe", "")
