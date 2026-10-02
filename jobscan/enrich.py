"""Snippet-only jobs (alert emails, Adzuna, Reed, Simplify) are dropped as
duplicates when the same job was also fetched in full from a company ATS.
The full ATS version is the one that gets judged."""
from __future__ import annotations

import re

from jobscan.models import RawJob
from jobscan.sponsors import normalise


def _key(company: str, title: str) -> tuple[str, str]:
    return normalise(company), re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def enrich(jobs: list[RawJob]) -> tuple[list[RawJob], int]:
    """Returns (jobs, number of snippet duplicates removed)."""
    full = {_key(j.company, j.title) for j in jobs if not j.light_data and j.description}
    out = [j for j in jobs if not (j.light_data and _key(j.company, j.title) in full)]
    return out, len(jobs) - len(out)
