"""Jooble API — https://jooble.org/api/about (free tier, requires a free API
key). Jooble is itself a meta-search aggregator, so it surfaces postings
mirrored from a wide range of other boards under one call.
"""

import logging

import httpx

from ...config import settings
from .base import RawJob, first_id
from .salary_parse import parse_salary_text

logger = logging.getLogger(__name__)

NAME = "jooble"


def is_configured() -> bool:
    return bool(settings.jooble_api_key)


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    if not is_configured():
        return []
    out: list[RawJob] = []
    with httpx.Client(timeout=15.0) as client:
        for term in search_terms:
            try:
                resp = client.post(
                    f"https://jooble.org/api/{settings.jooble_api_key}",
                    json={"keywords": term, "location": where, "page": "1"},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("[jooble] request failed for %r: %s", term, exc)
                continue
            except ValueError as exc:
                logger.warning("[jooble] bad JSON for %r: %s", term, exc)
                continue

            for item in data.get("jobs", []):
                try:
                    # Jooble doesn't give a stable numeric id in all responses;
                    # fall back to the link itself as the external identity.
                    ext_id = first_id(item.get("id"), item.get("link"))
                    title = (item.get("title") or "").strip()
                    if not ext_id or not title:
                        continue
                    comp_min, comp_max, comp_unit = parse_salary_text(item.get("salary", ""))
                    out.append(
                        RawJob(
                            source=NAME,
                            external_id=ext_id,
                            title=title,
                            company=(item.get("company") or "").strip(),
                            location=(item.get("location") or where).strip(),
                            description=item.get("snippet", ""),
                            comp_min=comp_min,
                            comp_max=comp_max,
                            comp_unit=comp_unit,
                            job_type=(item.get("type") or "Full-time"),
                            posted=(item.get("updated") or "")[:10],
                            url=item.get("link", ""),
                        )
                    )
                except Exception as exc:
                    logger.warning("[jooble] skipped malformed item: %s", exc)
    return out
