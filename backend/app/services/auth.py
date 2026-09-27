"""Owner authentication and server-side sessions (ADR-007).

Passwords: Argon2id via pwdlib. Sessions: opaque random tokens; only their SHA-256 is stored.
CSRF: HMAC of the session token, so it's bound to the session and never stored.
"""

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import cache

from pwdlib import PasswordHash
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import AuthSession, AuthUser

MIN_PASSWORD_LENGTH = 12
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")

_password_hash = PasswordHash.recommended()


class OwnerError(Exception):
    """A CLI-facing account problem (duplicate owner, weak password, unknown user)."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


@cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(session_token: str) -> str:
    digest = hmac.new(session_token.encode(), b"csrf", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def csrf_matches(session_token: str, presented: str | None) -> bool:
    return presented is not None and hmac.compare_digest(
        csrf_token_for(session_token).encode(), presented.encode()
    )


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise OwnerError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def create_owner(db: Session, username: str, password: str) -> AuthUser:
    if not USERNAME_PATTERN.fullmatch(username):
        raise OwnerError("Username must be 3-64 characters: letters, digits, '_', '.', '-'.")
    check_new_password(password)
    if db.scalar(select(func.count()).select_from(AuthUser)):
        raise OwnerError("An owner account already exists. Use set-password to rotate it.")
    user = AuthUser(username=username, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, username: str, password: str) -> AuthUser:
    """Rotate the password and revoke every existing session of the user."""
    check_new_password(password)
    user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    if user is None:
        raise OwnerError("No such user.")
    user.password_hash = hash_password(password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> AuthUser | None:
    """The user if the credentials are right and the account is active. The same work is done
    for unknown usernames, so timing doesn't reveal which usernames exist."""
    user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    if user is None:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


def start_session(
    db: Session, user: AuthUser, ttl: timedelta, previous_token: str | None = None
) -> str:
    """Create a session and return its raw token (to be sent only as the cookie). Removes the
    user's expired sessions and the session this browser presented, if any."""
    now = datetime.now(UTC)
    stale = AuthSession.expires_at <= now
    if previous_token:
        stale = stale | (AuthSession.token_hash == hash_token(previous_token))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, stale))
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=now + ttl))
    db.flush()
    return token


def get_active_session(db: Session, token: str) -> AuthSession | None:
    return db.scalar(
        select(AuthSession)
        .join(AuthSession.user)
        .options(joinedload(AuthSession.user))
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > datetime.now(UTC),
            AuthUser.is_active,
        )
    )


def end_session(db: Session, session: AuthSession) -> None:
    db.delete(session)
    db.flush()


class FailedLoginLimiter:
    """In-memory sliding-window count of failed logins per client key (IP).

    Per process and reset on restart: a local safeguard, not a production control (ADR-007 §8).
    """

    def __init__(self, max_failures: int = 10, window_seconds: float = 15 * 60) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        failures = self._failures.setdefault(key, deque())
        while failures and failures[0] <= now - self.window_seconds:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def blocked(self, key: str, now: float | None = None) -> bool:
        return len(self._recent(key, time.monotonic() if now is None else now)) >= (
            self.max_failures
        )

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._recent(key, now)
        self._failures.setdefault(key, deque()).append(now)
