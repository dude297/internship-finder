import logging

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api import auth, health, opportunities, profile
from app.api.deps import require_owner
from app.services.auth import FailedLoginLimiter

logger = logging.getLogger(__name__)

# Paths reachable without a session. Everything else is behind require_owner (ADR-007 §7).
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/login", "/api/auth/session"})


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Standard FastAPI shape, minus the echoed `input`/`ctx` (a rejected login must never echo
    # its password back or into logs).
    errors = [{k: e[k] for k in ("loc", "msg", "type") if k in e} for e in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Integrity error: %s", type(exc.orig).__name__)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "The change conflicts with existing data."},
    )


async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Internship Finder API", version="0.0.0")
    # No CORS middleware: the browser reaches the API same-origin (/api via a proxy), and
    # without Access-Control-Allow-Origin, browsers refuse cross-origin reads (ADR-007 §6).
    app.state.login_limiter = FailedLoginLimiter()
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, _integrity_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected_error)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.public_router, prefix="/api")

    private = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])
    private.include_router(auth.router)
    private.include_router(profile.router)
    private.include_router(opportunities.router)
    app.include_router(private)
    return app


app = create_app()
