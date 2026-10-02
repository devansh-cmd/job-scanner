"""Fallback for any other alert sender (Otta, Glassdoor, Totaljobs...).
Grabs links whose URL or text looks like a job. Noisy but better than nothing;
give a sender its own parser once you see its email format."""
from __future__ import annotations

import re

from jobscan.models import RawJob
from jobscan.parsers.common import block_lines, soup

LOOKS_LIKE_JOB = re.compile(r"job|career|vacanc|position|role", re.I)
SKIP = re.compile(r"unsubscribe|privacy|settings|preferences|help|manage", re.I)


def parse(body: str, sender: str = "") -> list[RawJob]:
    out, seen = [], set()
    src = "alert:" + (sender.split("@")[-1].strip("> ") or "unknown")
    for a in soup(body).find_all("a", href=True):
        href, text = a["href"], a.get_text(" ", strip=True)
        if len(text) < 6 or SKIP.search(href + text) or not LOOKS_LIKE_JOB.search(href):
            continue
        key = href.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        lines = block_lines(a)
        out.append(RawJob(
            source=src,
            company=lines[1] if len(lines) > 1 else "",
            title=text,
            url=href,
            location=lines[2] if len(lines) > 2 else "",
            description=" ".join(lines),
            light_data=True,
        ))
    return out
