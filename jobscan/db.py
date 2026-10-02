"""Supabase (Postgres) storage shared by the daily run and the dashboard.

The daily run inserts new jobs. The dashboard updates `status` and `notes`.
Inserts never touch an existing row, so your status is never overwritten.

Env / Streamlit secret: SUPABASE_DB_URL
Use Supabase's **Session pooler** connection string (IPv4). The "Direct
connection" string is IPv6-only and fails from GitHub Actions.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from jobscan.models import RoutedJob

STATUSES = ["new", "interested", "applied", "interviewing", "offer", "rejected", "hidden"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    first_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            TEXT,
    company           TEXT,
    title             TEXT,
    url               TEXT,
    location          TEXT,
    salary_min        INTEGER,
    salary_max        INTEGER,
    bucket            TEXT,        -- strong | check_manually | drop
    reasons           TEXT,
    role_family       TEXT,
    profile_match     INTEGER,
    ml_relevance      INTEGER,
    python_centrality INTEGER,
    sponsorship_p     REAL,
    on_register       BOOLEAN,
    light_data        BOOLEAN,
    rank_score        REAL,
    status            TEXT NOT NULL DEFAULT 'new',
    notes             TEXT NOT NULL DEFAULT '',
    status_updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_first_seen_idx ON jobs (first_seen DESC);
CREATE INDEX IF NOT EXISTS jobs_bucket_status_idx ON jobs (bucket, status);
"""

INSERT = """
INSERT INTO jobs (id, source, company, title, url, location, salary_min, salary_max,
                  bucket, reasons, role_family, profile_match, ml_relevance,
                  python_centrality, sponsorship_p, on_register, light_data, rank_score)
VALUES (%(id)s, %(source)s, %(company)s, %(title)s, %(url)s, %(location)s, %(salary_min)s,
        %(salary_max)s, %(bucket)s, %(reasons)s, %(role_family)s, %(profile_match)s,
        %(ml_relevance)s, %(python_centrality)s, %(sponsorship_p)s, %(on_register)s,
        %(light_data)s, %(rank_score)s)
ON CONFLICT (id) DO NOTHING
"""


def db_url() -> str | None:
    return os.environ.get("SUPABASE_DB_URL")


@contextmanager
def connect(url: str | None = None):
    # prepare_threshold=None: Supabase's pooler does not support prepared statements
    with psycopg.connect(url or db_url(), row_factory=dict_row, prepare_threshold=None,
                         connect_timeout=15) as conn:
        yield conn


def init(conn) -> None:
    conn.execute(SCHEMA)


def _row(r: RoutedJob) -> dict:
    v = r.verdict
    return {
        "id": r.job.id, "source": r.job.source, "company": r.job.company,
        "title": r.job.title, "url": r.job.url, "location": r.job.location,
        "salary_min": r.job.salary_min, "salary_max": r.job.salary_max,
        "bucket": r.bucket.value, "reasons": "; ".join(r.reasons),
        "role_family": v.fit.role_family.value if v else None,
        "profile_match": v.fit.profile_match if v else None,
        "ml_relevance": v.fit.ml_relevance if v else None,
        "python_centrality": v.fit.python_centrality if v else None,
        "sponsorship_p": v.gates.offers_sponsorship if v else None,
        "on_register": r.on_sponsor_register, "light_data": r.job.light_data,
        "rank_score": r.rank_score,
    }


def save(routed: list[RoutedJob], url: str | None = None) -> int:
    """Insert new jobs. Returns how many rows were actually added."""
    with connect(url) as conn:
        init(conn)
        before = conn.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"]
        with conn.cursor() as cur:
            cur.executemany(INSERT, [_row(r) for r in routed])
        after = conn.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"]
    return after - before


# ---------- used by the dashboard ----------

def load(conn, days: int) -> list[dict]:
    return conn.execute(
        "SELECT * FROM jobs WHERE first_seen >= now() - make_interval(days => %s) "
        "ORDER BY first_seen::date DESC, (bucket = 'strong') DESC, rank_score DESC NULLS LAST",
        (days,)).fetchall()


def update(conn, job_id: str, status: str, notes: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    conn.execute(
        "UPDATE jobs SET status=%s, notes=%s, status_updated_at=now() WHERE id=%s",
        (status, notes, job_id))
