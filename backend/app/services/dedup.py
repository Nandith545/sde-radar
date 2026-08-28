"""Cross-source deduplication.

The same real posting often shows up on more than one board with a
different external id, slightly different title wording, or a differently
formatted location. Exact-id matching (handled per-source via
`external_id`) only catches a re-fetch of the SAME board's SAME listing —
it does nothing for "this Blue Origin req is on both Adzuna and Jooble".
This module catches that second case.

Strategy: normalize company + title + location into a comparable form, do
an exact match first (fast path, covers the vast majority of true
duplicates), then fall back to a fuzzy title match scoped to the same
normalized company (never fuzzy-match across different companies).
"""

import difflib
import re

from sqlalchemy.orm import Session

from .. import models

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|plc|group)\b\.?", re.IGNORECASE
)
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")

FUZZY_TITLE_THRESHOLD = 0.87


def normalize_company(name: str) -> str:
    if not name:
        return ""
    n = name.lower()
    n = _SUFFIXES.sub("", n)
    n = _PUNCT.sub(" ", n)
    n = _WS.sub(" ", n).strip()
    return n


def normalize_title(title: str) -> str:
    if not title:
        return ""
    n = title.lower()
    n = _PUNCT.sub(" ", n)
    n = _WS.sub(" ", n).strip()
    return n


def normalize_location(location: str) -> str:
    if not location:
        return ""
    # Keep just the leading city-ish token so "Seattle, WA" and
    # "Seattle, Washington, US" both collapse to "seattle".
    first = location.split(",")[0]
    return _WS.sub(" ", _PUNCT.sub(" ", first.lower())).strip()


def make_dedup_key(title: str, company: str, location: str) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}|{normalize_location(location)}"


def find_duplicate(
    db: Session, *, title: str, company: str, location: str, exclude_id: int | None = None
) -> models.JobListing | None:
    """Return an existing JobListing that's almost certainly the same real
    posting, or None. Never crosses company boundaries.
    """
    company_norm = normalize_company(company)
    title_norm = normalize_title(title)
    if not company_norm or not title_norm:
        return None

    dedup_key = make_dedup_key(title, company, location)
    query = db.query(models.JobListing).filter(models.JobListing.dedup_key == dedup_key)
    if exclude_id is not None:
        query = query.filter(models.JobListing.id != exclude_id)
    exact = query.first()
    if exact:
        return exact

    # Fuzzy fallback: same normalized company, similar-enough title.
    candidates = db.query(models.JobListing).filter(models.JobListing.company_norm == company_norm)
    if exclude_id is not None:
        candidates = candidates.filter(models.JobListing.id != exclude_id)

    best: models.JobListing | None = None
    best_ratio = 0.0
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, title_norm, candidate.title_norm or "").ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = candidate
    if best and best_ratio >= FUZZY_TITLE_THRESHOLD:
        return best
    return None
