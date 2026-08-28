"""Adzuna Jobs API — https://developer.adzuna.com/ (free tier, requires a
free APP_ID + APP_KEY).
"""

import logging

import httpx

from ...config import settings
from .base import RawJob, first_id

logger = logging.getLogger(__name__)

NAME = "adzuna"


def is_configured() -> bool:
    return bool(settings.adzuna_app_id and settings.adzuna_app_key)


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    if not is_configured():
        return []
    out: list[RawJob] = []
    with httpx.Client(timeout=15.0) as client:
        for term in search_terms:
            try:
                resp = client.get(
                    "https://api.adzuna.com/v1/api/jobs/us/search/1",
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "what": term,
                        "where": where,
                        "results_per_page": 20,
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("[adzuna] request failed for %r: %s", term, exc)
                continue
            except ValueError as exc:
                logger.warning("[adzuna] bad JSON for %r: %s", term, exc)
                continue

            for item in data.get("results", []):
                try:
                    ext_id = first_id(item.get("id"), item.get("redirect_url"))
                    title = (item.get("title") or "").strip()
                    # A listing with no id or no title is unusable noise, and an
                    # id-less one would collide with every other id-less one.
                    if not ext_id or not title:
                        continue
                    out.append(
                        RawJob(
                            source=NAME,
                            external_id=ext_id,
                            title=title,
                            company=((item.get("company") or {}).get("display_name") or "").strip(),
                            location=((item.get("location") or {}).get("display_name") or where).strip(),
                            description=item.get("description", ""),
                            comp_min=item.get("salary_min"),
                            comp_max=item.get("salary_max"),
                            comp_unit="year",
                            job_type=(item.get("contract_time") or "full_time").replace("_", "-"),
                            posted=(item.get("created") or "")[:10],
                            url=item.get("redirect_url", ""),
                        )
                    )
                except Exception as exc:
                    logger.warning("[adzuna] skipped malformed item: %s", exc)
    return out
