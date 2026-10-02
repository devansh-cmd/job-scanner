"""Reads LinkedIn / Indeed / other job-alert emails from a Gmail label.

Setup (once): run scripts/gmail_auth.py on your laptop, then put
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in GitHub Secrets.
Scope is read-only.
"""
from __future__ import annotations

import base64
import os

from jobscan.models import RawJob
from jobscan.parsers import generic, indeed, linkedin
from jobscan.sources.base import Source

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# sender substring -> parser module
PARSERS = [
    ("linkedin.com", linkedin),
    ("indeed.com", indeed),
]


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


class GmailAlerts(Source):
    name = "gmail_alerts"

    def __init__(self, label: str = "job-alerts", newer_than: str = "2d"):
        self.query = f"label:{label} newer_than:{newer_than}"

    def fetch(self) -> list[RawJob]:
        svc = _service()
        msgs = svc.users().messages().list(userId="me", q=self.query, maxResults=200).execute()
        out: list[RawJob] = []
        for m in msgs.get("messages", []):
            full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
            headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
            sender = headers.get("from", "").lower()
            body = _html_body(full["payload"])
            parser = next((p for key, p in PARSERS if key in sender), generic)
            out.extend(parser.parse(body, sender=sender))
        return out
