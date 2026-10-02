"""Indeed job-alert emails. Job links carry a jk=<id> parameter."""
from __future__ import annotations

import re
from urllib.parse import unquote

from jobscan.models import RawJob
from jobscan.parsers.common import block_lines, soup, split_company_location

JK = re.compile(r"jk(?:=|%3D)([0-9a-f]{12,20})", re.I)


def parse(body: str, sender: str = "") -> list[RawJob]:
    out, seen = [], set()
    for a in soup(body).find_all("a", href=True):
        m = JK.search(unquote(a["href"]))
        if not m or m.group(1) in seen:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 4:
            continue
        seen.add(m.group(1))
        lines = block_lines(a)
        rest = [l for l in lines if l != title]
        company, location = split_company_location(rest[0]) if rest else ("", "")
        if not location and len(rest) > 1:
            location = rest[1]
        out.append(RawJob(
            source="indeed_alert",
            company=company,
            title=title,
            url=f"https://uk.indeed.com/viewjob?jk={m.group(1)}",
            location=location,
            description=" ".join(lines),
            light_data=True,
        ))
    return out
