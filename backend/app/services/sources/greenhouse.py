"""Greenhouse job boards — https://developers.greenhouse.io/job-board.html
(free, no API key).

Greenhouse is per-company, not a search engine: each employer exposes one
board at boards-api.greenhouse.io/v1/boards/{slug}/jobs as clean JSON. We
fetch every configured company's board and filter client-side by keyword and
location, exactly as the keyless keyword boards do.

`content=true` returns the full HTML description in one call, which avoids an
extra request per posting. The description is HTML; skill extraction and the
UI both already tolerate that (the seed data carries HTML too), so it is
stored as-is rather than stripped here.
"""

import html
import logging
import re

import httpx

from ...config import settings
from .base import RawJob, matches_filters

logger = logging.getLogger(__name__)

NAME = "greenhouse"

_TAG = re.compile(r"<[^>]+>")


def _companies() -> list[str]:
    return [c.strip() for c in settings.greenhouse_companies.split(",") if c.strip()]


def is_configured() -> bool:
    return bool(_companies())


def _plain_text(raw: str) -> str:
    """Greenhouse returns HTML-escaped HTML. Unescape, drop tags, collapse
    whitespace -- enough for keyword matching without pulling in a parser."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG.sub(" ", html.unescape(raw))).strip()


def _fetch_company(
    client: httpx.Client, slug: str, terms: list[str], where_tokens: list[str]
) -> list[RawJob]:
    out: list[RawJob] = []
    try:
        resp = client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        # One bad company slug must not sink the others, or a typo in the
        # configured list silently zeroes the whole connector.
        logger.warning("[greenhouse] %s request failed: %s", slug, exc)
        return out
    except ValueError as exc:
        logger.warning("[greenhouse] %s bad JSON: %s", slug, exc)
        return out

    for item in data.get("jobs", []):
        try:
            title = (item.get("title") or "").strip()
            job_id = item.get("id")
            if not title or job_id is None:
                continue
            location = ((item.get("location") or {}).get("name") or "").strip()
            if not matches_filters(title, location, terms, where_tokens):
                continue

            # The board name is the company. The live jobs endpoint often
            # omits it, so fall back to the slug title-cased for display.
            company = (data.get("name") or "").strip() or slug.replace("-", " ").title()
            out.append(
                RawJob(
                    source=NAME,
                    external_id=str(job_id),
                    title=title,
                    company=company,
                    location=location or "Unspecified",
                    description=_plain_text(item.get("content", "")),
                    comp_unit="year",
                    job_type="Full-time",
                    posted=(item.get("updated_at") or "")[:10],
                    url=item.get("absolute_url", ""),
                )
            )
        except Exception as exc:
            logger.warning("[greenhouse] %s skipped malformed item: %s", slug, exc)
    return out


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    companies = _companies()
    if not companies:
        return []
    terms = [t.lower() for t in search_terms]
    where_tokens = [t for t in where.lower().replace(",", " ").split() if len(t) > 2]

    out: list[RawJob] = []
    with httpx.Client(timeout=15.0) as client:
        for slug in companies:
            out.extend(_fetch_company(client, slug, terms, where_tokens))
    return out
