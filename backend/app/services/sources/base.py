"""Common shape every job-board connector normalizes into, so the ingestion
pipeline and the deduplication engine never need to know which board a
listing came from.
"""

from dataclasses import dataclass, field


@dataclass
class RawJob:
    source: str  # "adzuna" | "jooble" | "remotive" | "arbeitnow" | "seed"
    external_id: str  # unique within that source
    title: str
    company: str
    location: str
    description: str = ""
    comp_min: float | None = None
    comp_max: float | None = None
    comp_unit: str = "year"  # "year" | "hour"
    job_type: str = "Full-time"
    posted: str = ""  # ISO date (YYYY-MM-DD), best effort
    url: str = ""
    extra: dict = field(default_factory=dict)


def first_id(*candidates: object) -> str:
    """First usable identifier from the candidates, or "" if there is none.

    Exists because `str(item.get("id"))` on a missing key yields the *string*
    `"None"` — which is truthy, so it slips past `if not ext_id` checks and
    becomes a phantom listing. Worse, every id-less item then collides on the
    same identifier. Always route external ids through this.
    """
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return ""


def matches_filters(title: str, location: str, terms: list[str], where_tokens: list[str]) -> bool:
    """Whether a posting survives the keyword and location filters.

    Shared by every per-company board connector (Greenhouse, Lever, Ashby,
    SmartRecruiters). Those boards are not search engines -- they return one
    employer's entire req list -- so the filtering the keyword APIs do server
    side has to happen here instead, and it must happen identically or the
    same job would appear for one board and not another.

    A remote posting is never excluded by location: "remote" is an answer to
    "where", not a missing one.
    """
    if terms and not any(t in title.lower() for t in terms):
        return False
    loc = location.lower()
    if "remote" in loc:
        return True
    return not (where_tokens and location and not any(tok in loc for tok in where_tokens))
