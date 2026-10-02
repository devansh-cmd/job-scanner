"""SQLite memory of every job already seen, so each one is judged once.
The .db file is committed back to the repo by the GitHub Action."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobscan.models import RawJob, RoutedJob

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    source TEXT, company TEXT, title TEXT, url TEXT,
    bucket TEXT, reasons TEXT
);
"""


class Store:
    def __init__(self, path: str | Path = "data/jobs.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def filter_new(self, jobs: list[RawJob], ignore_history: bool = False) -> list[RawJob]:
        """Drop jobs seen in earlier runs (unless re-judging), and duplicates within this run."""
        out, ids = [], set()
        for j in jobs:
            if j.id in ids:
                continue
            ids.add(j.id)
            if ignore_history or self.db.execute("SELECT 1 FROM seen WHERE id=?", (j.id,)).fetchone() is None:
                out.append(j)
        return out

    def record(self, routed: list[RoutedJob]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.executemany(
            "INSERT OR IGNORE INTO seen VALUES (?,?,?,?,?,?,?,?)",
            [(r.job.id, now, r.job.source, r.job.company, r.job.title, r.job.url,
              r.bucket.value, "; ".join(r.reasons)) for r in routed])
        self.db.commit()
