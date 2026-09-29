"""Accounts and bearer tokens. Passwords use scrypt; tokens are stored only as SHA-256 hashes."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from autoeng.db.models import ApiToken, User
from autoeng.settings import get_settings

LOCAL_EMAIL = "local@autoeng.local"
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_user(db: Session, email: str, password: str, name: str) -> User:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ValueError("An account with this email already exists")
    user = User(email=email, name=name.strip() or email.split("@")[0], password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def issue_session(db: Session, user: User) -> str:
    token = new_token()
    db.add(ApiToken(user_id=user.id, token_hash=token_hash(token),
                    expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_days)))
    db.commit()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(token)))
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        return None
    return db.get(User, row.user_id)


def revoke(db: Session, token: str) -> None:
    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(token)))
    if row:
        db.delete(row)
        db.commit()


def local_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == LOCAL_EMAIL))
    if user is None:
        user = User(email=LOCAL_EMAIL, name="Local user", password_hash="!")
        db.add(user)
        db.commit()
    return user
