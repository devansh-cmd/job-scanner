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
