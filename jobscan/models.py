"""Shared data types. The Jev schema lives here: every field's `description`
is the natural-language question sent to the judge, so this file is the
single source of truth for what gets asked."""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------- Raw input (what every fetcher returns) ----------

class RawJob(BaseModel):
    source: str
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None
    light_data: bool = False  # True when we only have an alert-email snippet

    @property
    def id(self) -> str:
        canonical = self.url.split("?")[0].rstrip("/").lower()
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def as_text(self, max_chars: int = 12000) -> str:
        """What the judge reads."""
        sal = ""
        if self.salary_min or self.salary_max:
            sal = f"Salary: {self.salary_min or '?'} - {self.salary_max or '?'} GBP\n"
        return (
            f"Title: {self.title}\nCompany: {self.company}\nLocation: {self.location}\n"
            f"{sal}\n{self.description}"
        )[:max_chars]


# ---------- Judge output (the Jev schema) ----------

class RoleFamily(str, Enum):
    swe_ai_ml = "swe_ai_ml"
    product = "product_management"
    consulting = "tech_consulting"
    quant_dev = "quant_dev"
    data_science = "data_science"
    tech_risk = "tech_risk"
    other = "other"


class Gates(BaseModel):
    """Boolean questions, answered as P(yes). Any failed gate drops the job."""
    offers_sponsorship: float = Field(
        description="Does the posting say the employer offers UK visa sponsorship (Skilled Worker)?")
    no_sponsorship_wording: float = Field(
        description="Does the posting say candidates must already have the right to work in the UK, "
                    "or that sponsorship is not available?")
    accepts_sept_2027_finish: float = Field(
        description="Would a candidate finishing their MSc in September 2027 be eligible, "
                    "given any graduation window or start date in the posting?")
    max_2_years_experience: float = Field(
        description="Is this role open to candidates with 0 to 2 years of professional experience?")
    requires_clearance: float = Field(
        description="Does the role require SC or DV security clearance, or UK Government / defence work?")
    requires_a_level_maths: float = Field(
        description="Does the posting hard-require A-Level Maths or Further Maths?")
    uk_based: float = Field(
        description="Is the role based in the United Kingdom (including UK remote)?")


class Fit(BaseModel):
    """Choice and score questions. Used for ranking, never for dropping."""
    role_family: RoleFamily = Field(description="Which role family best describes this job?")
    python_centrality: int = Field(ge=1, le=5, description="How central is Python to this role? (1 none, 5 core)")
    ml_relevance: int = Field(ge=1, le=5, description="How much does this role involve ML or AI? (1 none, 5 core)")
    profile_match: int = Field(ge=1, le=5, description="How well does the candidate profile match this job? (1 poor, 5 excellent)")


class Flags(BaseModel):
    """Extra warnings shown in the digest. Never drop on their own."""
    agency_or_recruiter: float = Field(description="Is this posted by a recruitment agency rather than the employer?")
    one_app_per_cycle: float = Field(description="Does the employer allow only one application per recruitment cycle?")
    unpaid_or_commission: float = Field(description="Is the role unpaid or mainly commission-based?")


class JobVerdict(BaseModel):
    gates: Gates
    fit: Fit
    flags: Flags


# ---------- Routing output ----------

class Bucket(str, Enum):
    strong = "strong"
    check = "check_manually"
    drop = "drop"


class RoutedJob(BaseModel):
    job: RawJob
    verdict: JobVerdict | None = None
    on_sponsor_register: bool = False
    bucket: Bucket
    reasons: list[str] = []
    rank_score: float = 0.0
