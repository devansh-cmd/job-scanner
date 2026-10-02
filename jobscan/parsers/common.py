"""Shared helpers for alert-email parsers.

Alert email HTML changes now and then. Each parser finds job links by URL
pattern (stable) and reads title/company/location from the text around the
link (less stable). When a parser breaks, save a real alert email to
tests/fixtures/ and adjust the parser against it.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag


def soup(body: str) -> BeautifulSoup:
    return BeautifulSoup(body, "html.parser")


def block_lines(a: Tag, max_up: int = 4) -> list[str]:
    """Climb from a link to the nearest container holding a few lines of text,
    and return those lines. Typically: title, company, location."""
    node: Tag = a
    for _ in range(max_up):
        if node.parent is None:
            break
        node = node.parent
        lines = [l.strip() for l in node.get_text("\n").split("\n") if l.strip()]
        if len(lines) >= 3:
            return lines[:6]
    return [a.get_text(" ", strip=True)]


def split_company_location(line: str) -> tuple[str, str]:
    """'Monzo · London, England, United Kingdom' -> ('Monzo', 'London, ...')"""
    parts = re.split(r"\s+[·•|-]\s+", line, maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (line.strip(), "")
