"""Remotive API — https://remotive.com/api-documentation (free, no API key).
Remote-first tech job board; useful alongside city-specific boards since a
Seattle-based candidate is often also open to remote roles.
"""
import logging

import httpx

from .base import RawJob
from .salary_parse import parse_salary_text

logger = logging.getLogger(__name__)

NAME = "remotive"


def is_configured() -> bool:
    return True  # no key required


def fetch(search_terms: list[str], where: str) -> list[RawJob]:  # noqa: ARG001 - location isn't a filter here
    out: list[RawJob] = []
    seen_ids: set[str] = set()
    with httpx.Client(timeout=15.0) as client:
        for term in search_terms:
            try:
                resp = client.get("https://remotive.com/api/remote-jobs", params={"search": term, "limit": 20})
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("[remotive] request failed for %r: %s", term, exc)
                continue
            except ValueError as exc:
                logger.warning("[remotive] bad JSON for %r: %s", term, exc)
                continue

            for item in data.get("jobs", []):
                try:
                    ext_id = str(item.get("id", ""))
                    if not ext_id or ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)
                    comp_min, comp_max, comp_unit = parse_salary_text(item.get("salary", ""))
                    location = item.get("candidate_required_location", "Remote") or "Remote"
                    out.append(RawJob(
                        source=NAME,
                        external_id=ext_id,
                        title=(item.get("title") or "").strip() or "Untitled role",
                        company=(item.get("company_name") or "").strip(),
                        location=f"Remote ({location})",
                        description=item.get("description", ""),
                        comp_min=comp_min,
                        comp_max=comp_max,
                        comp_unit=comp_unit,
                        job_type=(item.get("job_type") or "Full-time").replace("_", "-"),
                        posted=(item.get("publication_date") or "")[:10],
                        url=item.get("url", ""),
                    ))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[remotive] skipped malformed item: %s", exc)
    return out
