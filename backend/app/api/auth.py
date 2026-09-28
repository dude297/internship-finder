import hmac
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import SESSION_COOKIE, DbSession, OwnerSession
from app.core.config import get_settings
from app.schemas.auth import LoginRequest, SessionResponse
from app.services import auth

# Public: login and session status. Private (mounted behind require_owner): logout.
public_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Invalid username or password."
PROXY_SECRET_HEADER = "X-IF-Proxy-Secret"
DIRECT_CLIENT = "direct"


def login_client_key(request: Request) -> str:
    """The failed-login throttle key for this request (ADR-009 §6).

    Only a request that proves it came through our Vercel proxy (the shared secret header) is
    keyed by X-Forwarded-For, which Vercel overwrites with the browser's address. Everything
    else, including direct calls to the Render URL, shares one key: their headers are ignored,
    so forging X-Forwarded-For buys nothing."""
    secret = get_settings().proxy_shared_secret
    presented = request.headers.get(PROXY_SECRET_HEADER)
    if (
        secret is None
        or presented is None
        or not hmac.compare_digest(secret.get_secret_value().encode(), presented.encode())
    ):
        return DIRECT_CLIENT
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return f"proxy:{forwarded or 'unknown'}"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


@public_router.post("/login")
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> SessionResponse:
    limiter: auth.FailedLoginLimiter = request.app.state.login_limiter
    client = login_client_key(request)
    if limiter.blocked(client):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed login attempts. Try again later."
        )
    user = auth.authenticate(db, body.username, body.password)
    if user is None:
        limiter.record_failure(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)
    token = auth.start_session(
        db,
        user,
        timedelta(hours=get_settings().session_ttl_hours),
        previous_token=request.cookies.get(SESSION_COOKIE),
    )
    db.commit()
    _set_session_cookie(response, token)
    return SessionResponse(
        authenticated=True, username=user.username, csrf_token=auth.csrf_token_for(token)
    )


@public_router.get("/session")
def get_session_status(request: Request, response: Response, db: DbSession) -> SessionResponse:
    token = request.cookies.get(SESSION_COOKIE)
    session = auth.get_active_session(db, token) if token else None
    if token is None or session is None:
        if token is not None:
            _clear_session_cookie(response)
        return SessionResponse(authenticated=False)
    return SessionResponse(
        authenticated=True, username=session.user.username, csrf_token=auth.csrf_token_for(token)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: OwnerSession, response: Response, db: DbSession) -> None:
    auth.end_session(db, session)
    db.commit()
    _clear_session_cookie(response)
