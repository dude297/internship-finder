"""Shared FastAPI dependencies, including the single private-API authorization boundary."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import AuthSession
from app.services import auth

SESSION_COOKIE = "if_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DbSession = Annotated[Session, Depends(get_session)]


def require_owner(request: Request, db: DbSession) -> AuthSession:
    """Authenticate the session cookie (401) and, for unsafe methods, the CSRF header (403).

    Mounted once on the parent router of every private endpoint (app.main)."""
    token = request.cookies.get(SESSION_COOKIE)
    session = auth.get_active_session(db, token) if token else None
    if token is None or session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    if request.method not in SAFE_METHODS and not auth.csrf_matches(
        token, request.headers.get(CSRF_HEADER)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")
    return session


OwnerSession = Annotated[AuthSession, Depends(require_owner)]
