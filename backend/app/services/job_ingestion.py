import logging

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from .. import models
from .skills import extract_skills
from .seed_jobs import SEED_JOBS

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_TERMS = [
    "Software Engineer",
    "Backend Engineer",
    "Full Stack Engineer",
    "AI Engineer",
    "Senior Software Engineer",
]


def _upsert_job(db: Session, *, source: str, external_id: str, title: str, company: str,
                 location: str, description: str, comp_min, comp_max, comp_unit: str,
                 job_type: str, posted: str, url: str) -> None:
    existing = db.query(models.JobListing).filter(models.JobListing.external_id == external_id).first()
    tags = extract_skills(f"{title}\n{description}")
    if existing:
        existing.title = title
        existing.company = company
        existing.location = location
        existing.description = description
        existing.comp_min = comp_min
        existing.comp_max = comp_max
        existing.comp_unit = comp_unit
        existing.job_type = job_type
        existing.posted = posted
        existing.url = url
        existing.skills = tags
    else:
        db.add(models.JobListing(
            source=source, external_id=external_id, title=title, company=company,
            location=location, description=description, comp_min=comp_min, comp_max=comp_max,
            comp_unit=comp_unit, job_type=job_type, posted=posted, url=url, skills=tags,
        ))


def seed_if_empty(db: Session) -> int:
    """Load the bundled seed dataset if the job pool is empty (first boot,
    or no Adzuna credentials configured). Safe to call repeatedly."""
    count = db.query(models.JobListing).count()
    if count > 0:
        return 0
    for job in SEED_JOBS:
        _upsert_job(
            db, source="seed", external_id=job["external_id"], title=job["title"],
            company=job["company"], location=job["location"], description=job["description"],
            comp_min=job["comp_min"], comp_max=job["comp_max"], comp_unit=job["comp_unit"],
            job_type=job["job_type"], posted=job["posted"], url=job["url"],
        )
    db.commit()
    return len(SEED_JOBS)


def refresh_from_adzuna(db: Session, *, what: str | None = None, where: str = "Seattle, WA",
                         search_terms: list[str] | None = None) -> int:
    """Pull fresh listings from the Adzuna Jobs API and upsert them into the
    shared job pool. No-ops (returns 0) if no API credentials are configured.
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        logger.info("Adzuna credentials not configured; skipping live ingestion.")
        return 0

    terms = search_terms or ([what] if what else DEFAULT_SEARCH_TERMS)
    added = 0
    with httpx.Client(timeout=15.0) as client:
        for term in terms:
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
                logger.warning("Adzuna request failed for '%s': %s", term, exc)
                continue

            for item in data.get("results", []):
                external_id = f"adzuna-{item.get('id')}"
                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                _upsert_job(
                    db,
                    source="adzuna",
                    external_id=external_id,
                    title=item.get("title", "").strip() or "Untitled role",
                    company=(item.get("company") or {}).get("display_name", ""),
                    location=(item.get("location") or {}).get("display_name", where),
                    description=item.get("description", ""),
                    comp_min=salary_min,
                    comp_max=salary_max,
                    comp_unit="year",
                    job_type=(item.get("contract_time") or "full_time").replace("_", "-"),
                    posted=(item.get("created") or "")[:10],
                    url=item.get("redirect_url", ""),
                )
                added += 1
    db.commit()
    return added
