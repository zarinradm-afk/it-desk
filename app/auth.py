import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

SESSION_COOKIE = "itdesk_session"
SESSION_HOURS = 12
MAX_FAILURES = 5
LOCK_WINDOW = timedelta(minutes=10)

_failures: dict[str, list[datetime]] = {}


class LoginRequired(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(digest, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: models.User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        models.LoginSession(
            token=_hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=SESSION_HOURS),
        )
    )
    db.commit()
    return token


def destroy_session(db: Session, token: str) -> None:
    row = db.get(models.LoginSession, _hash_token(token))
    if row:
        db.delete(row)
        db.commit()


def _recent_failures(key: str) -> list[datetime]:
    cutoff = utcnow() - LOCK_WINDOW
    _failures[key] = [t for t in _failures.get(key, []) if t > cutoff]
    return _failures[key]


def is_locked(key: str) -> bool:
    return len(_recent_failures(key)) >= MAX_FAILURES


def register_failure(key: str) -> None:
    _recent_failures(key).append(utcnow())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = db.get(models.LoginSession, _hash_token(token))
        if row and row.expires_at > utcnow():
            user = db.get(models.User, row.user_id)
            if user and user.is_active:
                return user
    raise LoginRequired()


def require_roles(*roles: str):
    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return dependency
