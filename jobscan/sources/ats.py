"""Greenhouse, Lever and Ashby public job-board APIs. No auth needed."""
from __future__ import annotations

from datetime import datetime, timezone

from jobscan.models import RawJob
from jobscan.sources.base import Source, get_json, html_to_text


class Greenhouse(Source):
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"greenhouse:{slug}"

    def fetch(self) -> list[RawJob]:
        data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{self.slug}/jobs?content=true")
        out = []
        for j in data.get("jobs", []):
            out.append(RawJob(
                source=self.name,
                company=j.get("company_name") or self.slug,
                title=j["title"],
                url=j["absolute_url"],
                location=(j.get("location") or {}).get("name", ""),
                description=html_to_text(j.get("content", "")),
                posted_at=j.get("updated_at"),
            ))
        return out


class Lever(Source):
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"lever:{slug}"

    def fetch(self) -> list[RawJob]:
        data = get_json(f"https://api.lever.co/v0/postings/{self.slug}?mode=json")
        out = []
        for j in data:
            cats = j.get("categories") or {}
            created = j.get("createdAt")
            out.append(RawJob(
                source=self.name,
                company=self.slug,
                title=j["text"],
                url=j["hostedUrl"],
                location=cats.get("location", "") or ", ".join(cats.get("allLocations", []) or []),
                description=j.get("descriptionPlain", "") + "\n" + html_to_text(
                    " ".join(l.get("content", "") for l in j.get("lists", []))),
                posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
            ))
        return out


class Ashby(Source):
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"ashby:{slug}"

    def fetch(self) -> list[RawJob]:
        data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{self.slug}?includeCompensation=true")
        out = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location", "")] + [
                s.get("location", "") for s in j.get("secondaryLocations", []) or []]
            out.append(RawJob(
                source=self.name,
                company=self.slug,
                title=j["title"],
                url=j["jobUrl"],
                location=", ".join(l for l in locs if l),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
                posted_at=j.get("publishedAt"),
            ))
        return out
