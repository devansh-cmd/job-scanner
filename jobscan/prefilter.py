"""Cheap rule-based drops before any judge call. Saves Jev calls and money.
Only drops on clear signals; anything unclear goes through to the judge."""
from __future__ import annotations

import re

from jobscan.models import RawJob

UK_MARKERS = re.compile(
    r"\b(united kingdom|uk|u\.k\.|england|scotland|wales|northern ireland|gb|great britain|"
    r"london|manchester|birmingham|bristol|leeds|edinburgh|glasgow|cambridge|oxford|"
    r"reading|newcastle|belfast|cardiff|sheffield|nottingham|liverpool|brighton|"
    r"southampton|leicester|coventry|milton keynes|northampton|bath|york|aberdeen|"
    r"dundee|guildford|slough|swindon|exeter|norwich|warwick|(?<!new )york|remote)\b", re.I)

# Explicit country words beat city names ("Cambridge, MA", "Birmingham, AL").
EXPLICIT_UK = re.compile(r"\b(united kingdom|uk|u\.k\.|england|scotland|wales|northern ireland|gb)\b", re.I)
NON_UK = re.compile(
    r",\s*[A-Z]{2}\b|(?i:\b(united states|usa|u\.s\.|canada|india|ireland|germany|france|netherlands|"
    r"spain|poland|singapore|hong kong|australia|new york|san francisco|seattle)\b)")

SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|head of|director|vp|vice president|"
    r"architect|chief|distinguished|fellow|partner|experienced|mid[- ]level|"
    r"(engineering|software|security|technical|delivery|program|programme|account|"
    r"sales|people|hiring|team|group product) manager)\b", re.I)
# Levelled titles: "Engineer II", "SRE III", "Software Engineer 3", "Data Scientist IV"
LEVELLED_TITLE = re.compile(r"\b(ii|iii|iv|[2-5])\b\s*(?=$|[),\-–(/|])", re.I)
# "Associate Product Manager" and "Graduate Product Manager" stay in.

INTERN_TITLE = re.compile(r"\b(intern|internship|placement|summer analyst|spring week|apprentice)\b", re.I)


def check(job: RawJob, salary_floor: int) -> str | None:
    """Return a drop reason, or None to keep."""
    loc = job.location
    if loc and not EXPLICIT_UK.search(loc):
        if NON_UK.search(loc) or not UK_MARKERS.search(loc):
            return "prefilter: not UK"
    if SENIOR_TITLE.search(job.title) or LEVELLED_TITLE.search(job.title):
        return "prefilter: senior title"
    if INTERN_TITLE.search(job.title):
        return "prefilter: internship / placement"
    top = job.salary_max or job.salary_min
    if top and 1000 < top < salary_floor:  # >1000 skips hourly/daily rates
        return f"prefilter: salary below £{salary_floor:,}"
    return None
