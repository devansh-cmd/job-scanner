"""Home Office register of licensed sponsors (Skilled Worker route).
Deterministic, free, strong signal. Cached in data/sponsors.csv for a day."""
from __future__ import annotations

import csv
import re
import time
from pathlib import Path

import requests

from jobscan.sources.base import HEADERS

PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
CACHE = Path("data/sponsors.csv")
MAX_AGE_S = 24 * 3600

SUFFIXES = re.compile(
    r"\b(limited|ltd|plc|llp|lp|inc|incorporated|group|holdings|uk|u\.k\.|"
    r"international|services|the|t/a.*)\b")


def normalise(name: str) -> str:
    name = name.lower().replace("&", " and ")
    name = SUFFIXES.sub(" ", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def _download() -> None:
    page = requests.get(PAGE, headers=HEADERS, timeout=30).text
    m = re.search(r'href="(https://assets\.publishing\.service\.gov\.uk/[^"]+\.csv)"', page)
    if not m:
        raise RuntimeError("Sponsor register CSV link not found on gov.uk page")
    r = requests.get(m.group(1), headers=HEADERS, timeout=120)
    r.raise_for_status()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(r.content)


class SponsorRegister:
    def __init__(self, refresh: bool = True):
        if refresh and (not CACHE.exists() or time.time() - CACHE.stat().st_mtime > MAX_AGE_S):
            _download()
        self.names: set[str] = set()
        if CACHE.exists():
            with CACHE.open(encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(f):
                    if "Skilled Worker" in (row.get("Route") or ""):
                        self.names.add(normalise(row.get("Organisation Name", "")))
        self.loaded = bool(self.names)

    def is_sponsor(self, company: str) -> bool:
        n = normalise(company)
        if not n or not self.loaded:
            return False
        if n in self.names:
            return True
        # "monzo" should match "monzo bank"; require a word boundary
        return any(s.startswith(n + " ") for s in self.names) if len(n) >= 4 else False
