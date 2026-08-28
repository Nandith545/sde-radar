"""Arbeitnow job board API — https://arbeitnow.com/api/job-board-api (free,
no API key). Returns a flat, unpaginated-by-search list, so we fetch the
board and filter client-side by keyword/location.
"""
import logging

import httpx

from .base import RawJob

logger = logging.getLogger(__name__)

NAME = "arbeitnow"


def is_configured() -> bool:
    return True  # no key required


def fetch(search_terms: list[str], where: str) -> list[RawJob]:
    out: list[RawJob] = []
    terms_lower = [t.lower() for t in search_terms]
    where_tokens = [t for t in where.lower().replace(",", " ").split() if len(t) > 2]

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://www.arbeitnow.com/api/job-board-api")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("[arbeitnow] request failed: %s", exc)
        return out
    except ValueError as exc:
        logger.warning("[arbeitnow] bad JSON: %s", exc)
        return out

    for item in data.get("data", []):
        try:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            haystack = f"{title} {' '.join(item.get('tags', []) or [])}".lower()
            if terms_lower and not any(t in haystack for t in terms_lower):
                continue

            is_remote = bool(item.get("remote"))
            location = item.get("location") or ("Remote" if is_remote else "")
            if not is_remote and where_tokens and location:
                if not any(tok in location.lower() for tok in where_tokens):
                    continue

            ext_id = str(item.get("slug") or item.get("url") or "")
            if not ext_id:
                continue

            job_types = item.get("job_types") or []
            job_type = job_types[0] if job_types else "Full-time"

            posted = ""
            created_at = item.get("created_at")
            if isinstance(created_at, (int, float)):
                import datetime
                posted = datetime.datetime.utcfromtimestamp(created_at).strftime("%Y-%m-%d")

            out.append(RawJob(
                source=NAME,
                external_id=ext_id,
                title=title,
                company=(item.get("company_name") or "").strip(),
                location=location or ("Remote" if is_remote else "Unspecified"),
                description=item.get("description", ""),
                comp_unit="year",
                job_type=job_type,
                posted=posted,
                url=item.get("url", ""),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[arbeitnow] skipped malformed item: %s", exc)
    return out
