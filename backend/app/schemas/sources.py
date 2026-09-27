import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import IngestionRunStatus, IngestionSourceKind, IngestionStage, SourceRegion


class SourceCreate(BaseModel):
    """Add a Greenhouse board or a Lever job site. `board` is a board token / site name or the
    public board URL; only the provider identifier is extracted and kept (the URL is never
    requested). The built-in discovery feed can't be created or re-pointed."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[IngestionSourceKind.GREENHOUSE, IngestionSourceKind.LEVER]
    display_name: str = Field(min_length=1, max_length=200)
    board: str = Field(min_length=1, max_length=500)
    # Lever only; a jobs.eu.lever.co link implies EU. Defaults to global.
    region: SourceRegion | None = None


class SourceUpdate(BaseModel):
    """Only the name and the enabled flag change. The provider identifier never does."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    enabled: bool


class RunErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_id: str | None
    stage: IngestionStage
    code: str
    message: str


class RunResponse(BaseModel):
    """Counts and safe error summaries only; never the fetched payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: IngestionRunStatus
    started_at: datetime
    finished_at: datetime | None
    source_generated_at: datetime | None
    fetched_count: int
    normalized_count: int
    created_count: int
    updated_count: int
    deduplicated_count: int
    unchanged_count: int
    closed_count: int
    reactivated_count: int
    invalid_count: int
    error_count: int
    error_summary: str | None
    errors: list[RunErrorResponse]


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: IngestionSourceKind
    key: str
    identifier: str
    region: SourceRegion | None
    display_name: str
    enabled: bool
    builtin: bool
    last_attempted_at: datetime | None
    last_success_at: datetime | None
    latest_run: RunResponse | None = None
