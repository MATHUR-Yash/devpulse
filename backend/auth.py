"""Password hashing and database-backed browser sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import BrowserSession, User

COOKIE = "devpulse_session"
SESSION_AGE = timedelta(days=7)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, expected: str) -> bool:
    salt, separator, _digest = expected.partition(":")
    if not separator or len(salt) != 32:
        return False
    try:
        return secrets.compare_digest(password_hash(password, salt), expected)
    except ValueError:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request, db: Session) -> User:
    token = request.cookies.get(COOKIE)
    session = db.get(BrowserSession, token_hash(token)) if token else None
    if session is None or session.expires_at <= utc_now():
        raise HTTPException(401, "Sign in to continue.")
    return session.user
