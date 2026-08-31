import logging
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..rate_limit import SlidingWindowRateLimiter
from ..security import create_access_token, dummy_verify, hash_password, verify_password
from ..services.job_facets import normalize_country
from ..services.regions import COUNTRIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

login_limiter = SlidingWindowRateLimiter(
    max_attempts=settings.login_rate_limit_attempts,
    window_seconds=settings.login_rate_limit_window_seconds,
)


def _client_ip(request: Request) -> str:
    # Render terminates TLS at its proxy, so the real client address arrives in
    # X-Forwarded-For. Take the first entry -- the rest are proxy hops.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _seniority(value: str) -> schemas.Seniority:
    """Same defensive read as _work_mode: a plain column, a closed API."""
    if value in ("entry", "mid", "senior"):
        return cast(schemas.Seniority, value)
    return ""


def _work_mode(value: str) -> schemas.WorkMode:
    """Read the plain-string column as the closed set the API promises.

    Pydantic guards writes, but the column itself is a free String, so a value
    written outside the API -- a fixture, a manual edit, a future migration --
    would otherwise 500 every read of this user. Anything unrecognised reads
    as "no preference", which is the same thing an empty column means.
    """
    if value in ("remote", "hybrid", "onsite"):
        return cast(schemas.WorkMode, value)
    return ""


def _clean_states(codes: list[str], target_country: str) -> list[str]:
    """Validate subdivision codes against the country they belong to.

    An unknown code is a 422 rather than a silent drop. Dropping it would
    *widen* the search rather than narrow it -- an empty list means "all
    states" -- so a typo would quietly return more jobs than asked for, which
    is the kind of wrong that never looks like an error.
    """
    if not codes:
        return []
    slug = normalize_country(target_country)
    if slug not in COUNTRIES:
        raise HTTPException(
            status_code=422,
            detail="Pick a country before selecting states.",
        )
    known = {sub.code for sub in COUNTRIES[slug].subdivisions}
    cleaned: list[str] = []
    for raw in codes:
        code = raw.strip().upper()
        if code not in known:
            raise HTTPException(
                status_code=422,
                detail=f"'{raw}' is not a region of {COUNTRIES[slug].label}.",
            )
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


def _user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        target_cities=user.target_cities or [],
        target_states=user.target_states or [],
        target_titles=user.target_titles,
        target_country=user.target_country,
        work_mode=_work_mode(user.work_mode),
        seniority=_seniority(user.seniority),
        min_salary=user.min_salary,
        address=user.address,
        phone=user.phone,
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
        target_cities=payload.target_cities,
        target_titles=payload.target_titles,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(subject=user.email)
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Key on email *and* IP: email alone lets an attacker lock a known user out
    # of their own account, IP alone is trivially sidestepped from a botnet.
    rate_key = f"{form.username.lower()}|{_client_ip(request)}"
    allowed, retry_after = login_limiter.check(rate_key)
    if not allowed:
        logger.warning("Login rate limit hit for %s", form.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(models.User).filter(models.User.email == form.username).first()

    if user is None:
        # Hash anyway. Skipping it would return "no such user" measurably
        # faster than "wrong password", which is enough to enumerate accounts.
        dummy_verify(form.password)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    # Succeeded, so don't leave someone who merely mistyped their password
    # throttled for the rest of the window.
    login_limiter.reset(rate_key)
    return schemas.Token(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return _user_out(current_user)


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.target_cities is not None:
        # Trimmed and de-duplicated here rather than in the UI, so the same
        # rules apply to anything hitting the API directly.
        seen: list[str] = []
        for city in payload.target_cities:
            trimmed = city.strip()
            if trimmed and trimmed.lower() not in [c.lower() for c in seen]:
                seen.append(trimmed)
        current_user.target_cities = seen
    if payload.target_titles is not None:
        current_user.target_titles = payload.target_titles

    # Country before states, and a changed country drops the old selection:
    # subdivision codes only mean anything inside one country, so carrying
    # "WA" from the United States into Australia would silently turn a
    # Washington preference into a Western Australia one.
    country_changed = (
        payload.target_country is not None and payload.target_country != current_user.target_country
    )
    if payload.target_country is not None:
        current_user.target_country = payload.target_country
    if payload.target_states is not None:
        current_user.target_states = _clean_states(payload.target_states, current_user.target_country)
    elif country_changed:
        current_user.target_states = []
    if payload.target_states is not None:
        current_user.target_states = _clean_states(payload.target_states, current_user.target_country)
    if payload.work_mode is not None:
        current_user.work_mode = payload.work_mode
    if payload.seniority is not None:
        current_user.seniority = payload.seniority
    if payload.min_salary is not None:
        # 0 clears the floor; NULL and 0 both mean 'no minimum' to scoring.
        current_user.min_salary = payload.min_salary or None
    if payload.address is not None:
        current_user.address = payload.address
    if payload.phone is not None:
        current_user.phone = payload.phone
    db.commit()
    db.refresh(current_user)
    return _user_out(current_user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: schemas.PasswordChange,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the password. Returns no body.

    The current password is required even though the caller already holds a
    valid token: otherwise a session left open on a shared machine is enough
    to lock the real owner out of their own account.

    Deliberately does not issue a new token. The JWT's subject is the email,
    which hasn't changed, and the token carries nothing derived from the
    password -- so the caller's existing one keeps working and a replacement
    would be pure ceremony. It would also mean handing a credential back out
    of a call that took a password as input, which is worth not doing when
    the call achieves nothing.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="That's already your password.")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    logger.info("Password changed for user id %s", current_user.id)

    # Tokens are stateless and carry no password reference, so sessions
    # elsewhere stay valid for their full lifetime. Real revocation needs a
    # token version column or a denylist; noted, and deliberately not faked
    # by minting a new token for this session alone.


@router.post("/email", response_model=schemas.Token)
def change_email(
    payload: schemas.EmailChange,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the sign-in address, returning a token for the new one.

    The JWT subject *is* the email, so the caller's existing token stops
    resolving the moment this commits. Returning a replacement is not a
    convenience -- without it the user is silently signed out mid-session.
    """
    new_email = payload.new_email.lower()
    if new_email == current_user.email.lower():
        raise HTTPException(status_code=400, detail="That's already your email address.")
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect.")

    taken = db.query(models.User).filter(models.User.email == new_email).first()
    if taken:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    current_user.email = new_email
    db.commit()
    logger.info("Email changed for user id %s", current_user.id)
    return schemas.Token(access_token=create_access_token(subject=new_email))
