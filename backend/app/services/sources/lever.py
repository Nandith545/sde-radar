"""Lever job boards — https://github.com/lever/postings-api (free, no key).

Like Greenhouse, Lever is per-company: each employer's postings live at
api.lever.co/v0/postings/{slug}?mode=json as a flat JSON list. We fetch every
configured company and filter client-side.

Lever already returns a plain-text `descriptionPlain`, so no HTML handling is
needed here.
"""

import datetime
import logging

import httpx

from ...config import settings
from .base import RawJob, matches_filters

logger = logging.getLogger(__name__)

NAME = "lever"


def _companies() -> list[str]:
    return [c.strip() for c in settings.lever_companies.split(",") if c.strip()]


def is_configured() -> bool:
    return bool(_companies())


def _fetch_company(
    client: httpx.Client, slug: str, terms: list[str], where_tokens: list[str]
) -> list[RawJob]:
    out: list[RawJob] = []
    try:
        resp = client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("[lever] %s request failed: %s", slug, exc)
        return out
    except ValueError as exc:
        logger.warning("[lever] %s bad JSON: %s", slug, exc)
        return out

    # Lever returns a bare list, not an object.
    if not isinstance(data, list):
        logger.warning("[lever] %s unexpected payload shape", slug)
        return out

    for item in data:
        try:
            title = (item.get("text") or "").strip()
            job_id = item.get("id")
            if not title or not job_id:
                continue
            categories = item.get("categories") or {}
            location = (categories.get("location") or "").strip()
            if not matches_filters(title, location, terms, where_tokens):
                continue

            posted = ""
            created = item.get("createdAt")
            if isinstance(created, int | float):
                # Lever timestamps are epoch milliseconds.
                posted = datetime.datetime.fromtimestamp(created / 1000, tz=datetime.UTC).strftime("%Y-%m-%d")

            out.append(
                RawJob(
                    source=NAME,
                    external_id=str(job_id),
                    title=title,
                    # The API doesn't name the employer, so use the slug the
                    # board is hosted under, title-cased for display.
                    company=slug.replace("-", " ").title(),
                    location=location or "Unspecified",
                    description=item.get("descriptionPlain", ""),
                    comp_unit="year",
                    job_type=(categories.get("commitment") or "Full-time").strip(),
                    posted=posted,
                    url=item.get("hostedUrl", ""),
                )
            )
        except Exception as exc:
            logger.warning("[lever] %s skipped malformed item: %s", slug, exc)
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
