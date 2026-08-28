import datetime

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# A real bcrypt hash of an unguessable value, used purely to burn the same
# CPU time as a genuine check when the account doesn't exist.
_DUMMY_HASH = pwd_context.hash("not-a-real-password-timing-equaliser")


def dummy_verify(plain: str) -> None:
    """Spends the same time a real password check would.

    Without this, a login for a non-existent account returns noticeably faster
    than one with a wrong password, which lets an attacker enumerate which
    email addresses have accounts.
    """
    pwd_context.verify(plain, _DUMMY_HASH)


def create_access_token(subject: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None
