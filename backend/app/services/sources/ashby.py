"""Ashby job boards — https://developers.ashbyhq.com/docs/public-job-posting-api
(free, no API key).

Per-company like Greenhouse and Lever: each employer exposes one board at
api.ashbyhq.com/posting-api/job-board/{slug} as clean JSON. We fetch every
configured company's board and filter client-side by keyword and location.

`includeCompensation=true` is worth the ask -- Ashby is one of the few boards
that publishes a salary range as a parseable string, and comp_min/comp_max
drive both the salary preference and the compensation sort. Most boards leave
those null.

Ashby returns `descriptionPlain` alongside the HTML, so no tag stripping is
needed here.
"""

import logging

import httpx

from ...config import settings
from .base import RawJob, first_id, matches_filters
from .salary_parse import parse_salary_text

logger = logging.getLogger(__name__)

NAME = "ashby"

# Ashby's own vocabulary, mapped onto the strings the UI and scoring expect.
# An unrecognised value falls through to the posting's raw label rather than
# being forced into "Full-time", which would misreport an internship.
_EMPLOYMENT_TYPES = {
    "FullTime": "Full-time",
    "PartTime": "Part-time",
    "Contract": "Contract",
    "Temporary": "Temporary",
    "Intern": "Internship",
}


def _companies() -> list[str]:
    return [c.strip() for c in settings.ashby_companies.split(",") if c.strip()]


def is_configured() -> bool:
    return bool(_companies())


def _location(job: dict) -> str:
    """Ashby's location string, with remote made explicit.

    On a remote req the field still names the office ("New York, NY (HQ)"),
    so without the suffix a remote job reads as onsite and gets filtered out
    for anyone targeting a different city. Ashby's own "(HQ)" marker is
    dropped first -- keeping it would render as "New York, NY (HQ) (Remote)",
    which looks like a bug on the job card.
    """
    text = (job.get("location") or "").strip()
    if text.endswith("(HQ)"):
        text = text[: -len("(HQ)")].strip()
    if not job.get("isRemote"):
        return text
    if "remote" in text.lower():
        return text
    return f"{text} (Remote)" if text else "Remote"


def _compensation(job: dict) -> tuple[float | None, float | None, str]:
    """Ashby's parseable salary summary, e.g. "$211.4K - $290.6K".

    The field is named `scrapeableCompensationSalarySummary` by Ashby -- it
    exists precisely so this string does not have to be read out of the
    human-facing tier summary, which carries equity and bonus text too.
    """
    comp = job.get("compensation") or {}
    return parse_salary_text(comp.get("scrapeableCompensationSalarySummary") or "")


def _fetch_company(
    client: httpx.Client, slug: str, terms: list[str], where_tokens: list[str]
) -> list[RawJob]:
    out: list[RawJob] = []
    try:
        resp = client.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            params={"includeCompensation": "true"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("[ashby] %s request failed: %s", slug, exc)
        return out
    except ValueError as exc:
        logger.warning("[ashby] %s returned unparseable JSON: %s", slug, exc)
        return out

    company = slug.replace("-", " ").title()
    for job in data.get("jobs", []) or []:
        try:
            # Ashby keeps unlisted drafts out of this feed already, but the
            # flag is explicit in the payload and cheap to honour -- a board
            # that starts including them shouldn't start leaking drafts.
            if job.get("isListed") is False:
                continue
            title = (job.get("title") or "").strip()
            location = _location(job)
            if not title or not matches_filters(title, location, terms, where_tokens):
                continue

            ext_id = first_id(job.get("id"))
            if not ext_id:
                continue

            comp_min, comp_max, comp_unit = _compensation(job)
            raw_type = job.get("employmentType") or ""
            out.append(
                RawJob(
                    source=NAME,
                    external_id=ext_id,
                    title=title,
                    company=company,
                    location=location or "Unspecified",
                    description=(job.get("descriptionPlain") or "").strip(),
                    comp_min=comp_min,
                    comp_max=comp_max,
                    comp_unit=comp_unit,
                    job_type=_EMPLOYMENT_TYPES.get(raw_type, raw_type or "Full-time"),
                    posted=(job.get("publishedAt") or "")[:10],
                    url=job.get("jobUrl") or job.get("applyUrl") or "",
                )
            )
        except Exception as exc:  # one bad posting must not kill the whole board
            logger.warning("[ashby] %s skipped a malformed posting: %s", slug, exc)
    return out


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    terms = [t.strip().lower() for t in search_terms if t.strip()]
    where_tokens = [w for w in where.lower().replace(",", " ").split() if len(w) > 2]

    out: list[RawJob] = []
    with httpx.Client(timeout=20.0) as client:
        for slug in _companies():
            out.extend(_fetch_company(client, slug, terms, where_tokens))
    logger.info("[ashby] %d matching postings across %d boards", len(out), len(_companies()))
    return out
