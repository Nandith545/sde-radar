"""SmartRecruiters job boards — https://dev.smartrecruiters.com/customer-api/posting-api/
(free, no API key).

Per-company like Greenhouse, Lever and Ashby, but with two differences that
shape this module.

**The boards are enormous.** Bosch alone publishes ~4,800 live postings. So
unlike the other per-company connectors, this one does not pull the whole
board: the list endpoint takes a `q` search parameter, and we spend one
request per configured search term instead of downloading everything and
discarding 99% of it client-side. `q` is fuzzy -- it still returns plenty of
non-matches -- so `matches_filters` runs over the results as usual.

**Descriptions live behind a second request.** The list response carries
title, location, company and date but no body text, and skill extraction is
what turns a posting into a useful match. Fetching every detail would mean
one HTTP call per result, so MAX_DETAIL_FETCHES caps it: postings past the
cap are still emitted, just without a description. A listing that appears
with weaker matching beats one the user never learns exists.
"""

import logging

import httpx

from ...config import settings
from .base import RawJob, first_id, matches_filters

logger = logging.getLogger(__name__)

NAME = "smartrecruiters"

_LIST_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"

# The API caps a page at 100 however many are asked for, so asking for more
# just makes the intent misleading.
PAGE_LIMIT = 100

# Per company, per refresh. Bounds a refresh at a predictable number of
# requests on a board with thousands of reqs.
MAX_DETAIL_FETCHES = 25

_EMPLOYMENT_TYPES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "part-time": "Part-time",
    "contract": "Contract",
    "temporary": "Temporary",
    "internship": "Internship",
    "intern": "Internship",
}


def _companies() -> list[str]:
    return [c.strip() for c in settings.smartrecruiters_companies.split(",") if c.strip()]


def is_configured() -> bool:
    return bool(_companies())


def _location(posting: dict) -> str:
    """Flatten SmartRecruiters' structured location into the freeform string
    the rest of the pipeline reads.

    Built as "City, REGION" to match the dominant shape of US postings
    elsewhere in the pool, which is what `infer_country` and the region
    inference are tuned to read.
    """
    loc = posting.get("location") or {}
    city = (loc.get("city") or "").strip()
    region = (loc.get("region") or "").strip()
    parts = [p for p in (city, region) if p]
    text = ", ".join(parts)
    if loc.get("remote"):
        return f"{text} (Remote)" if text else "Remote"
    if loc.get("hybrid") and text:
        return f"{text} (Hybrid)"
    return text


def _description(client: httpx.Client, slug: str, posting_id: str) -> str:
    """Job body from the detail endpoint, or "" if it can't be had.

    The text is assembled from the jobAd sections rather than one field --
    SmartRecruiters splits the posting across jobDescription, qualifications
    and additionalInformation, and the skills we want to extract are as often
    in qualifications as in the description proper.
    """
    try:
        resp = client.get(f"{_LIST_URL.format(slug=slug)}/{posting_id}")
        resp.raise_for_status()
        sections = (resp.json().get("jobAd") or {}).get("sections") or {}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[smartrecruiters] %s/%s detail failed: %s", slug, posting_id, exc)
        return ""

    chunks = [
        (sections.get(key) or {}).get("text") or ""
        for key in ("jobDescription", "qualifications", "additionalInformation")
    ]
    return " ".join(chunk for chunk in chunks if chunk).strip()


def _search_company(
    client: httpx.Client, slug: str, terms: list[str], where_tokens: list[str]
) -> list[RawJob]:
    seen: dict[str, dict] = {}
    # One query per term, deduplicated by posting id: the same req legitimately
    # answers to "software engineer" and "backend engineer".
    for term in terms or [""]:
        try:
            resp = client.get(
                _LIST_URL.format(slug=slug),
                params={"q": term, "limit": PAGE_LIMIT} if term else {"limit": PAGE_LIMIT},
            )
            resp.raise_for_status()
            content = resp.json().get("content") or []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[smartrecruiters] %s search %r failed: %s", slug, term, exc)
            continue
        for posting in content:
            ext_id = first_id(posting.get("id"), posting.get("uuid"))
            if ext_id:
                seen.setdefault(ext_id, posting)

    out: list[RawJob] = []
    details_used = 0
    for ext_id, posting in seen.items():
        try:
            title = (posting.get("name") or "").strip()
            location = _location(posting)
            if not title or not matches_filters(title, location, terms, where_tokens):
                continue

            description = ""
            if details_used < MAX_DETAIL_FETCHES:
                description = _description(client, slug, ext_id)
                details_used += 1

            raw_type = (posting.get("typeOfEmployment") or {}).get("label") or ""
            out.append(
                RawJob(
                    source=NAME,
                    external_id=ext_id,
                    title=title,
                    company=(posting.get("company") or {}).get("name") or slug,
                    location=location or "Unspecified",
                    description=description,
                    job_type=_EMPLOYMENT_TYPES.get(raw_type.lower(), raw_type or "Full-time"),
                    posted=(posting.get("releasedDate") or "")[:10],
                    # The list response carries no link -- applyUrl and
                    # postingUrl exist only on the detail record, which most
                    # postings never fetch. This canonical form is built from
                    # data every posting has and resolves to the same page, so
                    # nothing lands in the pool without a working Apply button.
                    url=f"https://jobs.smartrecruiters.com/{slug}/{ext_id}",
                )
            )
        except Exception as exc:  # one bad posting must not kill the whole board
            logger.warning("[smartrecruiters] %s skipped a malformed posting: %s", slug, exc)
    return out


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    terms = [t.strip().lower() for t in search_terms if t.strip()]
    where_tokens = [w for w in where.lower().replace(",", " ").split() if len(w) > 2]

    out: list[RawJob] = []
    with httpx.Client(timeout=20.0) as client:
        for slug in _companies():
            out.extend(_search_company(client, slug, terms, where_tokens))
    logger.info("[smartrecruiters] %d matching postings across %d boards", len(out), len(_companies()))
    return out
