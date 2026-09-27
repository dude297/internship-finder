"""The source registry (ADR-008 §1): list, add, rename/enable, and run history."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.enums import IngestionSourceKind
from app.ingestion.adapters import greenhouse, lever
from app.models import IngestionRun, IngestionSource
from app.schemas.sources import RunResponse, SourceCreate, SourceResponse, SourceUpdate


class SourceConflict(Exception):
    """The same provider board/site is already configured."""


def to_response(source: IngestionSource, latest: IngestionRun | None) -> SourceResponse:
    response = SourceResponse.model_validate(source)
    response.latest_run = RunResponse.model_validate(latest) if latest else None
    return response


def latest_runs(db: Session) -> dict[uuid.UUID, IngestionRun]:
    rows = db.scalars(
        select(IngestionRun)
        .options(selectinload(IngestionRun.errors))
        .ext(distinct_on(IngestionRun.source_id))
        .order_by(IngestionRun.source_id, IngestionRun.started_at.desc(), IngestionRun.id.desc())
    ).all()
    return {run.source_id: run for run in rows}


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
        kind=body.kind, identifier=identifier, region=region, display_name=body.display_name
    )
    db.add(source)
    db.flush()
    return source


def update_source(source: IngestionSource, body: SourceUpdate) -> None:
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
