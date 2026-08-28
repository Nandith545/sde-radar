"""Common shape every job-board connector normalizes into, so the ingestion
pipeline and the deduplication engine never need to know which board a
listing came from.
"""
from dataclasses import dataclass, field


@dataclass
class RawJob:
    source: str            # "adzuna" | "jooble" | "remotive" | "arbeitnow" | "seed"
    external_id: str       # unique within that source
    title: str
    company: str
    location: str
    description: str = ""
    comp_min: float | None = None
    comp_max: float | None = None
    comp_unit: str = "year"     # "year" | "hour"
    job_type: str = "Full-time"
    posted: str = ""             # ISO date (YYYY-MM-DD), best effort
    url: str = ""
    extra: dict = field(default_factory=dict)
