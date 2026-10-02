"""Turns judge probabilities into buckets: Strong / Check manually / Drop.
Plain code on purpose: thresholds are in settings.yaml and easy to tune."""
from __future__ import annotations

from jobscan.models import Bucket, JobVerdict, RawJob, RoleFamily, RoutedJob


def route(job: RawJob, verdict: JobVerdict | Exception, on_register: bool, cfg: dict) -> RoutedJob:
    if isinstance(verdict, Exception):
        return RoutedJob(job=job, on_sponsor_register=on_register, bucket=Bucket.check,
                         reasons=[f"judge error: {type(verdict).__name__}"])

    g, f, fl = verdict.gates, verdict.fit, verdict.flags
    t = cfg["gates"]

    drops = []
    if g.no_sponsorship_wording > t["no_sponsorship_wording_max"]:
        drops.append("no sponsorship / right-to-work wording")
    if g.requires_clearance > t["requires_clearance_max"]:
        drops.append("security clearance")
    if g.requires_a_level_maths > t["requires_a_level_maths_max"]:
        drops.append("A-Level Maths required")
    if g.accepts_sept_2027_finish < t["accepts_sept_2027_finish_min"]:
        drops.append("graduation window / start date")
    if g.max_2_years_experience < t["max_2_years_experience_min"]:
        drops.append("not entry level (0 to 2 years)")
    if g.uk_based < t["uk_based_min"]:
        drops.append("not UK")

    # Rank: role preference first, then fit. PM ignores Python centrality.
    rank = cfg["role_rank"].get(f.role_family.value, 0) * 10 + f.profile_match * 2 + f.ml_relevance
    if f.role_family != RoleFamily.product:
        rank += f.python_centrality
    if on_register:
        rank += 5

    if drops:
        return RoutedJob(job=job, verdict=verdict, on_sponsor_register=on_register,
                         bucket=Bucket.drop, reasons=drops, rank_score=rank)

    s = cfg["strong"]
    sponsor_ok = on_register or g.offers_sponsorship >= s["offers_sponsorship_min"]
    reasons = []
    reasons.append("on sponsor register" if on_register else
                   f"sponsorship P={g.offers_sponsorship:.2f}")
    reasons.append(f"{f.role_family.value}, match {f.profile_match}/5")
    if job.light_data:
        reasons.append("light data (snippet only)")
    if fl.agency_or_recruiter > 0.7:
        reasons.append("agency posting")
    if fl.one_app_per_cycle > 0.7:
        reasons.append("one application per cycle")

    strong = sponsor_ok and f.profile_match >= s["profile_match_min"] and not job.light_data
    if not strong:
        if not sponsor_ok:
            reasons.append("sponsorship unclear")
        if job.light_data and sponsor_ok:
            reasons.append("open the link to confirm")
    return RoutedJob(job=job, verdict=verdict, on_sponsor_register=on_register,
                     bucket=Bucket.strong if strong else Bucket.check,
                     reasons=reasons, rank_score=rank)
