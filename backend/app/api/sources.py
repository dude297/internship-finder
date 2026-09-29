import uuid
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import DbSession
from app.ingestion.http import configured_transport
from app.ingestion.pipeline import SyncInProgress, sync_enabled_sources, sync_source
from app.models import IngestionSource
from app.schemas.sources import RunResponse, SourceCreate, SourceResponse, SourceUpdate
from app.services import sources as service

router = APIRouter(prefix="/sources", tags=["sources"])

# The network by default; tests (and the E2E fixture setting) replace it. Never user-controlled.
Transport = Annotated[httpx2.BaseTransport | None, Depends(configured_transport)]


def _load(db: DbSession, source_id: uuid.UUID) -> IngestionSource:
    source = db.get(IngestionSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
    return source


@router.get("")
def list_sources(db: DbSession) -> list[SourceResponse]:
    latest = service.latest_runs(db)
    return [service.to_response(s, latest.get(s.id)) for s in service.list_sources(db)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SourceResponse)
def create_source(body: SourceCreate, db: DbSession) -> SourceResponse | JSONResponse:
    try:
        source = service.create_source(db, body)
    except ValueError as error:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [{"loc": ["body", "board"], "msg": str(error), "type": "value_error"}]
            },
        )
    except service.SourceConflict as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return service.to_response(source, None)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: uuid.UUID, body: SourceUpdate, db: DbSession
) -> SourceResponse | JSONResponse:
    source = _load(db, source_id)
    try:
        service.update_source(source, body)
    except ValueError as error:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [{"loc": ["body", "scope"], "msg": str(error), "type": "value_error"}]
            },
        )
    db.commit()
    return service.to_response(source, service.latest_runs(db).get(source.id))


@router.post("/sync")
def sync_all(db: DbSession, transport: Transport) -> list[RunResponse]:
    """Sync every enabled source in turn (one failing doesn't stop the others). The pipeline
    commits its own run bookkeeping and item savepoints (ADR-008 §4)."""
    return [
        RunResponse.model_validate(run) for run in sync_enabled_sources(db, transport=transport)
    ]


@router.post("/{source_id}/sync")
def sync_one(source_id: uuid.UUID, db: DbSession, transport: Transport) -> RunResponse:
    source = _load(db, source_id)
    if not source.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Enable this source before syncing it.")
    try:
        run = sync_source(db, source, transport=transport)
    except SyncInProgress as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return RunResponse.model_validate(run)


@router.get("/{source_id}/runs")
def list_runs(
    source_id: uuid.UUID, db: DbSession, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[RunResponse]:
    _load(db, source_id)
    return [RunResponse.model_validate(run) for run in service.list_runs(db, source_id, limit)]
