"""The source registry (ADR-008 §1): list, add, rename/enable, and run history."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.enums import IngestionRunStatus, IngestionSourceKind, SourceScope
from app.ingestion.adapters import ashby, greenhouse, lever
from app.models import IngestionRun, IngestionSource
from app.schemas.sources import RunResponse, SourceCreate, SourceResponse, SourceUpdate
from app.services.source_health import derive_health


class SourceConflict(Exception):
    """The same provider board/site is already configured."""


def to_response(
    source: IngestionSource,
    latest: IngestionRun | None,
    latest_finished_status: IngestionRunStatus | None,
    consecutive_failures: int,
    now: datetime,
) -> SourceResponse:
    response = SourceResponse.model_validate(source)
    response.latest_run = RunResponse.model_validate(latest) if latest else None
    health = derive_health(
        enabled=source.enabled,
        latest_finished_status=latest_finished_status,
        last_success_at=source.last_success_at,
        consecutive_failures=consecutive_failures,
        now=now,
    )
    response.health = health.health
    response.consecutive_failures = health.consecutive_failures
    response.last_success_age_hours = health.last_success_age_hours
    return response


def latest_runs(db: Session) -> dict[uuid.UUID, IngestionRun]:
    rows = db.scalars(
        select(IngestionRun)
        .options(selectinload(IngestionRun.errors))
        .ext(distinct_on(IngestionRun.source_id))
        .order_by(IngestionRun.source_id, IngestionRun.started_at.desc(), IngestionRun.id.desc())
    ).all()
    return {run.source_id: run for run in rows}


def latest_finished_statuses(
    db: Session, source_ids: Sequence[uuid.UUID] | None = None
) -> dict[uuid.UUID, IngestionRunStatus]:
    """The newest non-RUNNING run's status per source (health is judged by the latest *finished*
    run, not a run still in progress). One query for every source given, never a per-source
    loop."""
    stmt = (
        select(IngestionRun.source_id, IngestionRun.status)
        .ext(distinct_on(IngestionRun.source_id))
        .where(IngestionRun.status != IngestionRunStatus.RUNNING)
    )
    if source_ids is not None:
        stmt = stmt.where(IngestionRun.source_id.in_(source_ids))
    stmt = stmt.order_by(
        IngestionRun.source_id, IngestionRun.started_at.desc(), IngestionRun.id.desc()
    )
    return dict(db.execute(stmt).all())


def consecutive_failure_counts(
    db: Session, source_ids: Sequence[uuid.UUID] | None = None
) -> dict[uuid.UUID, int]:
    """FAILED/PARTIAL runs newer than each source's `last_success_at` (or all of them, if it has
    never succeeded). Every run newer than the last success is, by definition, not a success
    (a success would have moved that boundary), so this is just a count — one query across every
    source given, never a per-source loop."""
    stmt = (
        select(IngestionRun.source_id, func.count())
        .join(IngestionSource, IngestionSource.id == IngestionRun.source_id)
        .where(
            IngestionRun.status.in_((IngestionRunStatus.FAILED, IngestionRunStatus.PARTIAL)),
            or_(
                IngestionSource.last_success_at.is_(None),
                IngestionRun.started_at > IngestionSource.last_success_at,
            ),
        )
    )
    if source_ids is not None:
        stmt = stmt.where(IngestionRun.source_id.in_(source_ids))
    stmt = stmt.group_by(IngestionRun.source_id)
    return dict(db.execute(stmt).all())


def health_for(db: Session, source: IngestionSource) -> tuple[IngestionRunStatus | None, int]:
    """The two health inputs for a single source (create/update responses); `list_sources`
    computes these for every source at once instead."""
    ids = [source.id]
    return (
        latest_finished_statuses(db, ids).get(source.id),
        consecutive_failure_counts(db, ids).get(source.id, 0),
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


def list_sources(db: Session) -> list[IngestionSource]:
    return list(
        db.scalars(
            select(IngestionSource).order_by(IngestionSource.created_at, IngestionSource.id)
        ).all()
    )


def create_source(db: Session, body: SourceCreate) -> IngestionSource:
    """Raises ValueError for an unusable board reference, SourceConflict for a duplicate."""
    region = None
    if body.kind is IngestionSourceKind.GREENHOUSE:
        if body.region is not None:
            raise ValueError("Greenhouse boards don't have a region.")
        identifier = greenhouse.parse_board_reference(body.board)
    elif body.kind is IngestionSourceKind.ASHBY:
        if body.region is not None:
            raise ValueError("Ashby boards don't have a region.")
        identifier = ashby.parse_board_reference(body.board)
    else:
        identifier, region = lever.parse_site_reference(body.board, body.region)
    duplicate = db.scalars(
        select(IngestionSource).where(
            IngestionSource.kind == body.kind,
            IngestionSource.identifier == identifier,
            IngestionSource.region.is_(None)
            if region is None
            else IngestionSource.region == region,
        )
    ).first()
    if duplicate is not None:
        raise SourceConflict(f"{duplicate.display_name} is already configured.")
    source = IngestionSource(
        kind=body.kind,
        identifier=identifier,
        region=region,
        display_name=body.display_name,
        scope=body.scope,
    )
    db.add(source)
    db.flush()
    return source


def update_source(source: IngestionSource, body: SourceUpdate) -> None:
    """Raises ValueError when the built-in feed is asked to filter.

    A scope change clears the HTTP validators, so the next sync fetches and applies a full
    snapshot instead of getting a 304 (ADR-010 §10)."""
    if body.scope is not None and body.scope is not source.scope:
        if source.builtin and body.scope is not SourceScope.ALL:
            raise ValueError("The built-in discovery feed always imports every posting.")
        source.scope = body.scope
        source.etag = None
        source.last_modified = None
    source.display_name = body.display_name
    source.enabled = body.enabled


def list_runs(db: Session, source_id: uuid.UUID, limit: int) -> list[IngestionRun]:
    return list(
        db.scalars(
            select(IngestionRun)
            .where(IngestionRun.source_id == source_id)
            .options(selectinload(IngestionRun.errors))
            .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
            .limit(limit)
        ).all()
    )
