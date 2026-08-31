"""Orchestrates pulling listings from every configured job-board connector,
deduplicating across them, and upserting into the shared job pool.
"""

import logging

from sqlalchemy.orm import Session

from .. import models
from .dedup import find_duplicate, make_dedup_key, normalize_company, normalize_title
from .seed_jobs import SEED_JOBS
from .skills import extract_skills
from .sources import REGISTRY, SEED_SOURCE, active_sources
from .sources.base import RawJob

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_TERMS = [
    "Software Engineer",
    "Backend Engineer",
    "Full Stack Engineer",
    "AI Engineer",
    "Senior Software Engineer",
]


def _apply_fields(job: models.JobListing, raw: RawJob) -> None:
    """Fill in fields on an existing/new row from a freshly-fetched RawJob,
    without clobbering better data that's already there (e.g. don't erase a
    real comp range with a blank one from a source that lacks salary data).
    """
    # Keep the canonical title/company/location stable once set, so a posting
    # doesn't "flap" in the UI (e.g. "Senior Software Engineer" <-> "Sr.
    # Software Engineer") just because a different connector's wording
    # happened to be ingested last. Only fill these in on first sight.
    job.title = job.title or raw.title
    job.company = job.company or raw.company
    job.location = job.location or raw.location
    if raw.description and len(raw.description) > len(job.description or ""):
        job.description = raw.description
    if raw.comp_min is not None and job.comp_min is None:
        job.comp_min = raw.comp_min
        job.comp_max = raw.comp_max
        job.comp_unit = raw.comp_unit
    job.job_type = job.job_type or raw.job_type
    if raw.posted and (not job.posted or raw.posted > job.posted):
        job.posted = raw.posted
    job.url = job.url or raw.url
    job.dedup_key = make_dedup_key(job.title, job.company, job.location)
    job.company_norm = normalize_company(job.company)
    job.title_norm = normalize_title(job.title)
    job.skills = extract_skills(f"{job.title}\n{job.description}")


def _record_source(job: models.JobListing, raw: RawJob) -> None:
    entries = list(job.sources or [])
    if not any(e.get("name") == raw.source and e.get("external_id") == raw.external_id for e in entries):
        entries.append({"name": raw.source, "external_id": raw.external_id, "url": raw.url})
    job.sources = entries


def _ingest_raw_jobs(db: Session, raw_jobs: list[RawJob]) -> dict:
    # Build a fast lookup of every (source, external_id) pair we already know
    # about, across every canonical job row -- covers the case where a
    # posting was previously merged in as a secondary source.
    by_source_id: dict[tuple[str, str], models.JobListing] = {}
    for job in db.query(models.JobListing).all():
        for entry in job.sources or []:
            name = entry.get("name")
            ext_id = entry.get("external_id")
            # Skip malformed entries rather than keying the map on None --
            # a single bad row would otherwise collide with every other
            # incomplete entry and merge unrelated postings together.
            if isinstance(name, str) and isinstance(ext_id, str):
                by_source_id[(name, ext_id)] = job

    added = 0
    merged = 0
    updated = 0

    for raw in raw_jobs:
        key = (raw.source, raw.external_id)
        existing = by_source_id.get(key)
        if existing:
            _apply_fields(existing, raw)
            _record_source(existing, raw)
            updated += 1
            continue

        duplicate = find_duplicate(db, title=raw.title, company=raw.company, location=raw.location)
        if duplicate:
            _apply_fields(duplicate, raw)
            _record_source(duplicate, raw)
            by_source_id[key] = duplicate
            merged += 1
            continue

        job = models.JobListing(external_id=f"{raw.source}:{raw.external_id}", source=raw.source, sources=[])
        _apply_fields(job, raw)
        _record_source(job, raw)
        db.add(job)
        db.flush()  # assign an id so later fuzzy-dedup lookups in this same run can see it
        by_source_id[key] = job
        added += 1

    db.commit()
    return {"added": added, "merged_into_existing": merged, "same_source_updates": updated}


def seed_if_empty(db: Session) -> int:
    """Load the bundled seed dataset if the job pool is empty (first boot,
    or no connectors configured at all). Safe to call repeatedly."""
    if db.query(models.JobListing).count() > 0:
        return 0
    raw_jobs = [
        RawJob(
            source=SEED_SOURCE,
            external_id=job["external_id"],
            title=job["title"],
            company=job["company"],
            location=job["location"],
            description=job["description"],
            comp_min=job["comp_min"],
            comp_max=job["comp_max"],
            comp_unit=job["comp_unit"],
            job_type=job["job_type"],
            posted=job["posted"],
            url=job["url"],
        )
        for job in SEED_JOBS
    ]
    result = _ingest_raw_jobs(db, raw_jobs)
    return result["added"]


def refresh_from_all_sources(
    db: Session, *, search_terms: list[str] | None = None, where: str = "Seattle, WA"
) -> dict:
    """Pull fresh listings from every connector that has credentials
    configured, dedup them against each other and the existing pool, and
    upsert. No-ops gracefully (returns zero counts) if nothing is
    configured -- the seed pool stays in place.
    """
    terms = search_terms or DEFAULT_SEARCH_TERMS
    sources_used = active_sources()
    if not sources_used:
        logger.info("No job-board connectors configured; staying on the seed pool.")
        return {"added": 0, "merged_into_existing": 0, "same_source_updates": 0, "sources_used": []}

    raw_jobs: list[RawJob] = []
    for module in REGISTRY:
        if not module.is_configured():
            continue
        try:
            fetched = module.fetch(terms, where)
        except Exception as exc:
            logger.warning("[%s] connector raised an exception, skipping: %s", module.NAME, exc)
            continue
        logger.info("[%s] fetched %d listings", module.NAME, len(fetched))
        raw_jobs.extend(fetched)

    result = _ingest_raw_jobs(db, raw_jobs)
    result["sources_used"] = sources_used
    logger.info(
        "Refresh complete: %d new, %d merged into existing postings, %d same-source updates (sources: %s)",
        result["added"],
        result["merged_into_existing"],
        result["same_source_updates"],
        ", ".join(sources_used),
    )
    return result
