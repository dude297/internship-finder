from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.enums import IngestionSourceKind
from app.models import IngestionSource
from app.services.source_health import WARNING_WITHIN_HOURS
from app.services.sources import utcnow

router = APIRouter(prefix="/status", tags=["status"])


class FreshnessStatus(BaseModel):
    last_successful_sync_at: datetime | None
    age_hours: float | None
    stale: bool
    reason: Literal["ok", "stale", "never_synced", "no_sources"]


@router.get("/freshness")
def read_data_age(db: DbSession) -> FreshnessStatus:
    return freshness_status(db)


def freshness_status(db: Session) -> FreshnessStatus:
    """Newest successful sync across enabled automated sources (the registry file never syncs);
    `stale` once it is older than the source-health warning window. One statement. Stale never
    means closed (ADR-015): this only says the scheduler may have stopped."""
    count, newest = db.execute(
        select(func.count(), func.max(IngestionSource.last_success_at)).where(
            IngestionSource.enabled.is_(True),
            IngestionSource.kind != IngestionSourceKind.CURATED_REGISTRY,
        )
    ).one()
    if count == 0:
        return FreshnessStatus(
            last_successful_sync_at=None, age_hours=None, stale=False, reason="no_sources"
        )
    if newest is None:
        return FreshnessStatus(
            last_successful_sync_at=None, age_hours=None, stale=True, reason="never_synced"
        )
    age = (utcnow() - newest).total_seconds() / 3600
    stale = age > WARNING_WITHIN_HOURS
    return FreshnessStatus(
        last_successful_sync_at=newest,
        age_hours=round(age, 1),
        stale=stale,
        reason="stale" if stale else "ok",
    )
