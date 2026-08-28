"""Resume and cover-letter versions, and the files themselves.

Uploads are immutable: a revision is a new row, never an overwrite. The whole
point is to still be able to open the exact document that was sent with an
application weeks after sending it, which an in-place edit would destroy.
"""

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.resume_parser import extract_text

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB, matching the resume upload.
ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")
KINDS = ("resume", "cover_letter")


def _to_out(doc: models.UserDocument) -> schemas.DocumentOut:
    # The bytes are deliberately absent: listing documents shouldn't ship
    # several megabytes of PDF to render a filename.
    return schemas.DocumentOut(
        id=doc.id,
        kind=doc.kind,  # type: ignore[arg-type]
        label=doc.label,
        filename=doc.filename,
        size_bytes=doc.size_bytes,
        created_at=doc.created_at,
    )


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = (
        db.query(models.UserDocument)
        .filter(models.UserDocument.user_id == current_user.id)
        .order_by(models.UserDocument.created_at.desc())
        .all()
    )
    return [_to_out(d) for d in docs]


@router.post("", response_model=schemas.DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    kind: str = Form("resume"),
    label: str = Form(""),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if kind not in KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of: {', '.join(KINDS)}.")

    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload a .pdf, .txt, or .md file.")

    # Checked before reading so an oversized upload is refused without first
    # buffering the whole thing into memory.
    if file.size is not None and file.size > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (5MB max).")
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (5MB max).")
    if not content:
        raise HTTPException(status_code=400, detail="That file is empty.")

    # Text is extracted now rather than on demand: the parse can fail on a
    # malformed PDF, and failing at upload is far easier to act on than
    # failing later when someone is trying to read the thing back.
    raw_text = extract_text(filename, content)

    doc = models.UserDocument(
        user_id=current_user.id,
        kind=kind,
        label=label.strip()[:120],
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        content=content,
        raw_text=raw_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = (
        db.query(models.UserDocument)
        .filter(
            models.UserDocument.id == document_id,
            # Scoped to the owner: without this, sequential ids would let any
            # signed-in user read anyone else's resume.
            models.UserDocument.user_id == current_user.id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return StreamingResponse(
        io.BytesIO(doc.content),
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = (
        db.query(models.UserDocument)
        .filter(
            models.UserDocument.id == document_id,
            models.UserDocument.user_id == current_user.id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # A document attached to an application is the record of what was sent.
    # Deleting it would leave the application pointing at nothing, so refuse
    # and name the applications instead of silently unlinking them.
    attached = (
        db.query(models.UserJobMatch)
        .filter(
            (models.UserJobMatch.resume_document_id == document_id)
            | (models.UserJobMatch.cover_letter_document_id == document_id)
        )
        .count()
    )
    if attached:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This is attached to {attached} application"
                f"{'s' if attached != 1 else ''}. Detach it there first."
            ),
        )

    db.delete(doc)
    db.commit()
