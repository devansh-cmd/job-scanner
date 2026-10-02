"""Reads job-alert emails (LinkedIn, Indeed, Student Circus, Milkround,
Bristol mycareer, Bright Network, Prospects, TargetJobs, Otta) from a Gmail label.

Which sender maps to which parser is set in config/settings.yaml (alert_senders).

Setup (once): run scripts/gmail_auth.py on your laptop, then put
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in GitHub Secrets.
Scope is read-only.
"""
from __future__ import annotations

import base64
import os
from collections import Counter

from jobscan.models import RawJob
from jobscan.parsers import generic, indeed, linkedin
from jobscan.sources.base import Source

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PARSER_MODULES = {"linkedin": linkedin, "indeed": indeed, "generic": generic}


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _html_body(payload: dict) -> str:
    """Walk MIME parts, return the first text/html body (fallback text/plain)."""
    stack, plain = [payload], ""
    while stack:
        part = stack.pop()
        stack.extend(part.get("parts", []) or [])
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if part.get("mimeType") == "text/html":
            return decoded
        if part.get("mimeType") == "text/plain":
            plain = decoded
    return plain


def match_sender(sender: str, senders: list[dict]) -> dict | None:
    sender = sender.lower()
    return next((s for s in senders if s["match"].lower() in sender), None)


def parse_email(body: str, sender: str, senders: list[dict]) -> list[RawJob]:
    """Route one alert email to its parser and tag jobs with the board name."""
    cfg = match_sender(sender, senders)
    parser = PARSER_MODULES[cfg["parser"]] if cfg else generic
    jobs = parser.parse(body, sender=sender)
    name = f"{cfg['name']}_alert" if cfg else None
    if name:
        for j in jobs:
            j.source = name
    return jobs


class GmailAlerts(Source):
    name = "gmail_alerts"

    def __init__(self, senders: list[dict], label: str = "job-alerts", newer_than: str = "2d"):
        self.senders = senders
        self.query = f"label:{label} newer_than:{newer_than}"
        self.emails_by_sender: Counter = Counter()  # for the coverage table

    def fetch(self) -> list[RawJob]:
        svc = _service()
        msgs = svc.users().messages().list(userId="me", q=self.query, maxResults=200).execute()
        out: list[RawJob] = []
        for m in msgs.get("messages", []):
            full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
            headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
            sender = headers.get("from", "")
            cfg = match_sender(sender, self.senders)
            self.emails_by_sender[cfg["name"] if cfg else "unmatched"] += 1
            out.extend(parse_email(_html_body(full["payload"]), sender, self.senders))
        return out
