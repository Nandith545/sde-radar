from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.job_facets import FRESHNESS_WINDOWS, MAX_AGE_DAYS, job_age_days
from ..services.job_ingestion import refresh_from_all_sources
from ..services.matching import preference_mismatch, score_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _source_names(job: models.JobListing) -> list[str]:
    names = []
    for entry in job.sources or []:
        name = entry.get("name")
        if name and name not in names:
            names.append(name)
    return names or [job.source]


def _to_job_out(
    job: models.JobListing,
    status: models.StatusEnum,
    notes: str,
    result,
    mismatch: str | None = None,
    match: models.UserJobMatch | None = None,
) -> schemas.JobOut:
    return schemas.JobOut(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        comp_min=job.comp_min,
        comp_max=job.comp_max,
        comp_unit=job.comp_unit,
        job_type=job.job_type,
        posted=job.posted,
        url=job.url,
        skills=job.skills,
        sources=_source_names(job),
        score=result.score,
        reason=result.reason,
        flag=result.flag,
        matches_preferences=mismatch is None,
        mismatch_reason=mismatch,
        resume_document_id=match.resume_document_id if match else None,
        cover_letter_document_id=match.cover_letter_document_id if match else None,
        status=status,
        notes=notes,
    )


def _matched_jobs(db: Session, user: models.User, within_days: int = MAX_AGE_DAYS) -> list[schemas.JobOut]:
    """Scored jobs, newest first, with anything past the age limit dropped.

    `within_days` is clamped to MAX_AGE_DAYS: the ceiling is a property of the
    product, not a default the caller can raise by passing a bigger number.

    A posting whose age cannot be established at all is kept. That case needs
    both an unparseable `posted` and a missing created_at, which no ingested
    row has -- but dropping it silently is the failure mode worth avoiding,
    since the user would never learn the listing existed.
    """
    within_days = min(within_days, MAX_AGE_DAYS)
    resume = db.query(models.Resume).filter(models.Resume.user_id == user.id).first()
    jobs = db.query(models.JobListing).all()
    match_map = {
        m.job_id: m
        for m in db.query(models.UserJobMatch).filter(models.UserJobMatch.user_id == user.id).all()
    }

    out = []
    for job in jobs:
        age = job_age_days(job.posted or "", job.created_at)
        if age is not None and age > within_days:
            continue
        result = score_job(job, user, resume)
        existing = match_map.get(job.id)
        status = existing.status if existing else models.StatusEnum.new
        notes = existing.notes if existing else ""
        entry = _to_job_out(job, status, notes, result, preference_mismatch(job, user), existing)
        out.append((age if age is not None else MAX_AGE_DAYS + 1, entry))

    # Newest first, then by score so same-day postings still lead with the
    # best match rather than whatever order the database returned.
    out.sort(key=lambda pair: (pair[0], -pair[1].score))
    return [entry for _, entry in out]


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(
    posted_within: str = Query(
        "30d",
        description="One of 1d, 7d, 14d, 30d. Anything older than 30 days is never returned.",
    ),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    days = FRESHNESS_WINDOWS.get(posted_within)
    if days is None:
        raise HTTPException(
            status_code=422,
            detail=f"posted_within must be one of: {', '.join(FRESHNESS_WINDOWS)}.",
        )
    return _matched_jobs(db, current_user, days)


@router.get("/stats", response_model=schemas.StatsOut)
def job_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = _matched_jobs(db, current_user)
    total = len(jobs)
    avg = round(sum(j.score for j in jobs) / total) if total else 0
    return schemas.StatsOut(
        total=total,
        avg_score=avg,
        applied=sum(1 for j in jobs if j.status == models.StatusEnum.applied),
        interviewing=sum(1 for j in jobs if j.status == models.StatusEnum.interviewing),
        offers=sum(1 for j in jobs if j.status == models.StatusEnum.offer),
    )


@router.patch("/{job_id}", response_model=schemas.JobOut)
def update_match(
    job_id: int,
    payload: schemas.MatchUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(models.JobListing).filter(models.JobListing.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    match = (
        db.query(models.UserJobMatch)
        .filter(models.UserJobMatch.user_id == current_user.id, models.UserJobMatch.job_id == job_id)
        .first()
    )
    if not match:
        match = models.UserJobMatch(user_id=current_user.id, job_id=job_id)
        db.add(match)
    if payload.status is not None:
        match.status = payload.status
    if payload.notes is not None:
        match.notes = payload.notes
    for field in ("resume_document_id", "cover_letter_document_id"):
        value = getattr(payload, field)
        if value is None:
            continue
        if value == 0:
            setattr(match, field, None)
            continue
        owned = (
            db.query(models.UserDocument)
            .filter(
                models.UserDocument.id == value,
                # Scoped to the owner, so a guessed id can't attach someone
                # else's resume to your application.
                models.UserDocument.user_id == current_user.id,
            )
            .first()
        )
        if not owned:
            raise HTTPException(status_code=404, detail="Document not found.")
        setattr(match, field, value)
    db.commit()

    resume = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).first()
    result = score_job(job, current_user, resume)
    return _to_job_out(job, match.status, match.notes, result, preference_mismatch(job, current_user), match)


# Each city is a separate round of calls to every configured board, so this
# caps how much of a user's free-tier quota one button press can spend.
# Cities beyond the cap are still filtered on -- they just rely on the
# scheduled refresh and other users' pulls to populate the shared pool.
MAX_REFRESH_CITIES = 3


@router.post("/refresh")
def refresh_jobs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    titles = [t.strip() for t in (current_user.target_titles or "").split(",") if t.strip()] or None
    cities = (current_user.target_cities or [])[:MAX_REFRESH_CITIES]

    if not cities:
        return refresh_from_all_sources(db, search_terms=titles)

    # Fetching only the first city would leave the others permanently empty:
    # the user would filter for Austin roles that were never pulled and read
    # the blank result as the filter being broken.
    counts = {"added": 0, "merged_into_existing": 0, "same_source_updates": 0}
    sources_used: list[str] = []
    for city in cities:
        result = refresh_from_all_sources(db, where=city, search_terms=titles)
        for key in counts:
            counts[key] += result.get(key, 0)
        for name in result.get("sources_used", []):
            if name not in sources_used:
                sources_used.append(name)
    return {**counts, "sources_used": sources_used}
