"""Common plumbing for every fetcher."""
from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod

import requests

from jobscan.models import RawJob

HEADERS = {"User-Agent": "job-scanner/0.1 (personal job alert tool)"}
TIMEOUT = 30


def get_json(url: str, **kw):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


def html_to_text(raw: str) -> str:
    """Strip tags and unescape. Good enough for judging, no layout needed."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


class Source(ABC):
    """One job source. `fetch` returns RawJobs; errors are caught by main.py
    and shown in the digest's coverage table, so a broken source is visible."""
    name: str = "source"

    @abstractmethod
    def fetch(self) -> list[RawJob]: ...
