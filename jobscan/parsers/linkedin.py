"""LinkedIn job-alert emails. Job links contain /jobs/view/<id>."""
from __future__ import annotations

import re

from jobscan.models import RawJob
from jobscan.parsers.common import block_lines, soup, split_company_location

JOB_ID = re.compile(r"/jobs/view/(\d+)")


def parse(body: str, sender: str = "") -> list[RawJob]:
    out, seen = [], set()
    for a in soup(body).find_all("a", href=True):
        m = JOB_ID.search(a["href"])
        if not m or m.group(1) in seen:
            continue
        lines = block_lines(a)
        title = a.get_text(" ", strip=True) or lines[0]
        if len(title) < 4:  # image/logo link, the text link comes later
            continue
        seen.add(m.group(1))
        rest = [l for l in lines if l != title]
        company, location = split_company_location(rest[0]) if rest else ("", "")
        if not location and len(rest) > 1:
            location = rest[1]
        out.append(RawJob(
            source="linkedin_alert",
            company=company,
            title=title,
            url=f"https://www.linkedin.com/jobs/view/{m.group(1)}/",
            location=location,
            description=" ".join(lines),
            light_data=True,
        ))
    return out
