from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.resume_parser import parse_resume

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")


@router.post("", response_model=schemas.ResumeOut)
async def upload_resume(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload a .pdf, .txt, or .md file.")
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (5MB max).")

    parsed = parse_resume(file.filename, content)
    if not parsed["skills"]:
        raise HTTPException(
            status_code=422,
            detail="Couldn't detect any recognizable technical skills in this file. "
                   "Make sure it's a text-based resume (not a scanned image).",
        )

    resume = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).first()
    if resume:
        resume.filename = file.filename
        resume.raw_text = parsed["raw_text"]
        resume.skills = parsed["skills"]
        resume.years_experience = parsed["years_experience"]
    else:
        resume = models.Resume(
            user_id=current_user.id, filename=file.filename, raw_text=parsed["raw_text"],
            skills=parsed["skills"], years_experience=parsed["years_experience"],
        )
        db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=schemas.ResumeOut)
def get_resume(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    resume = db.query(models.Resume).filter(models.Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="No resume uploaded yet.")
    return resume
