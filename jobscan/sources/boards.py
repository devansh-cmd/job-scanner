"""Job boards with official APIs: Adzuna, Reed, plus the SimplifyJobs repo."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

from jobscan.models import RawJob
from jobscan.sources.base import HEADERS, TIMEOUT, Source, get_json, html_to_text


class Adzuna(Source):
    """Free key: developer.adzuna.com. Env: ADZUNA_APP_ID, ADZUNA_APP_KEY."""
    name = "adzuna"

    def __init__(self, terms: list[str], max_days_old: int = 2):
        self.terms = terms
        self.max_days_old = max_days_old

    def fetch(self) -> list[RawJob]:
        app_id, app_key = os.environ["ADZUNA_APP_ID"], os.environ["ADZUNA_APP_KEY"]
        out = []
        for term in self.terms:
            data = get_json(
                "https://api.adzuna.com/v1/api/jobs/gb/search/1",
                params={"app_id": app_id, "app_key": app_key, "what": term,
                        "results_per_page": 50, "max_days_old": self.max_days_old,
                        "content-type": "application/json"})
            for j in data.get("results", []):
                out.append(RawJob(
                    source=self.name,
                    company=(j.get("company") or {}).get("display_name", ""),
                    title=j.get("title", ""),
                    url=j["redirect_url"],
                    location=(j.get("location") or {}).get("display_name", ""),
                    description=html_to_text(j.get("description", "")),
                    salary_min=int(j["salary_min"]) if j.get("salary_min") else None,
                    salary_max=int(j["salary_max"]) if j.get("salary_max") else None,
                    posted_at=j.get("created"),
                    light_data=True,  # Adzuna descriptions are truncated
                ))
        return out


class Reed(Source):
    """Free key: reed.co.uk/developers. Env: REED_API_KEY."""
    name = "reed"

    def __init__(self, terms: list[str]):
        self.terms = terms

    def fetch(self) -> list[RawJob]:
        key = os.environ["REED_API_KEY"]
        out = []
        for term in self.terms:
            r = requests.get("https://www.reed.co.uk/api/1.0/search",
                             params={"keywords": term, "resultsToTake": 100},
                             auth=(key, ""), headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            for j in r.json().get("results", []):
                posted = None
                if j.get("date"):
                    try:
                        posted = datetime.strptime(j["date"], "%d/%m/%Y").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                out.append(RawJob(
                    source=self.name,
                    company=j.get("employerName", ""),
                    title=j.get("jobTitle", ""),
                    url=j["jobUrl"],
                    location=j.get("locationName", ""),
                    description=html_to_text(j.get("jobDescription", "")),
                    salary_min=int(j["minimumSalary"]) if j.get("minimumSalary") else None,
                    salary_max=int(j["maximumSalary"]) if j.get("maximumSalary") else None,
                    posted_at=posted,
                    light_data=True,  # search results carry a snippet only
                ))
        return out


class SimplifyNewGrad(Source):
    """Community-maintained new-grad list on GitHub. Titles + links only."""
    name = "simplify_newgrad"
    URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"

    def __init__(self, max_age_days: int = 14):
        self.max_age_days = max_age_days

    def fetch(self) -> list[RawJob]:
        cutoff = datetime.now(timezone.utc).timestamp() - self.max_age_days * 86400
        out = []
        for j in get_json(self.URL):
            if not (j.get("active") and j.get("is_visible", True)):
                continue
            if (j.get("date_posted") or 0) < cutoff:
                continue
            out.append(RawJob(
                source=self.name,
                company=j.get("company_name", ""),
                title=j.get("title", ""),
                url=j["url"],
                location="; ".join(j.get("locations", [])),
                description=f"Category: {j.get('category', '')}. Sponsorship note: {j.get('sponsorship', '')}.",
                posted_at=datetime.fromtimestamp(j["date_posted"], tz=timezone.utc),
                light_data=True,
            ))
        return out
