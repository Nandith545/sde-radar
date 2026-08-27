from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id, email=user.email, full_name=user.full_name,
        target_city=user.target_city, target_titles=user.target_titles,
        has_resume=user.resume is not None,
    )


@router.post("/register", response_model=schemas.Token)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user = models.User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        target_city=payload.target_city,
        target_titles=payload.target_titles,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(subject=user.email)
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = create_access_token(subject=user.email)
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return _user_out(current_user)


@router.patch("/me", response_model=schemas.UserOut)
def update_me(payload: schemas.UserUpdate, current_user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.target_city is not None:
        current_user.target_city = payload.target_city
    if payload.target_titles is not None:
        current_user.target_titles = payload.target_titles
    db.commit()
    db.refresh(current_user)
    return _user_out(current_user)
