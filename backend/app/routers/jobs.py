from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.matching import score_job
from ..services.job_ingestion import refresh_from_adzuna

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _matched_jobs(db: Session, user: models.User) -> list[schemas.JobOut]:
    resume = db.query(models.Resume).filter(models.Resume.user_id == user.id).first()
    jobs = db.query(models.JobListing).all()
    match_map = {
        m.job_id: m for m in db.query(models.UserJobMatch).filter(models.UserJobMatch.user_id == user.id).all()
    }

    out = []
    for job in jobs:
        result = score_job(job, user, resume)
        existing = match_map.get(job.id)
        status = existing.status if existing else models.StatusEnum.new
        notes = existing.notes if existing else ""
        out.append(schemas.JobOut(
            id=job.id, title=job.title, company=job.company, location=job.location,
            comp_min=job.comp_min, comp_max=job.comp_max, comp_unit=job.comp_unit,
            job_type=job.job_type, posted=job.posted, url=job.url, skills=job.skills,
            score=result.score, reason=result.reason, flag=result.flag,
            status=status, notes=notes,
        ))
    out.sort(key=lambda j: -j.score)
    return out


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _matched_jobs(db, current_user)


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
def update_match(job_id: int, payload: schemas.MatchUpdate, current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    job = db.query(models.JobListing).filter(models.JobListing.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    match = db.query(models.UserJobMatch).filter(
        models.UserJobMatch.user_id == current_user.id, models.UserJobMatch.job_id == job_id
    ).first()
    if not match:
        match = models.UserJobMatch(user_id=current_user.id, job_id=job_id)
        db.add(match)
    if payload.status is not None:
        match.status = payload.status
    if payload.notes is not None:
        match.notes = payload.notes
    db.commit()

    resume = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).first()
    result = score_job(job, current_user, resume)
    return schemas.JobOut(
        id=job.id, title=job.title, company=job.company, location=job.location,
        comp_min=job.comp_min, comp_max=job.comp_max, comp_unit=job.comp_unit,
        job_type=job.job_type, posted=job.posted, url=job.url, skills=job.skills,
        score=result.score, reason=result.reason, flag=result.flag,
        status=match.status, notes=match.notes,
    )


@router.post("/refresh")
def refresh_jobs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    titles = [t.strip() for t in (current_user.target_titles or "").split(",") if t.strip()] or None
    added = refresh_from_adzuna(db, where=current_user.target_city, search_terms=titles)
    return {"added_or_updated": added}
