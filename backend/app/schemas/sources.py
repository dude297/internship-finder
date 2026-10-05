import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    IngestionRunStatus,
    IngestionSourceKind,
    IngestionStage,
    SourceRegion,
    SourceScope,
)


class SourceCreate(BaseModel):
    """Add a Greenhouse board, a Lever job site, an Ashby job board, or a SmartRecruiters
    company. `board` is a board token / site name / company identifier or the public board URL;
    only the provider identifier is extracted and kept (the URL is never requested). The
    built-in sources (discovery feed, program registry) can't be created or re-pointed."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        IngestionSourceKind.GREENHOUSE,
        IngestionSourceKind.LEVER,
        IngestionSourceKind.ASHBY,
        IngestionSourceKind.SMARTRECRUITERS,
        IngestionSourceKind.WORKABLE,
        IngestionSourceKind.PINPOINT,
    ]
    display_name: str = Field(min_length=1, max_length=200)
    board: str = Field(min_length=1, max_length=500)
    # Lever only; a jobs.eu.lever.co link implies EU. Defaults to global.
    region: SourceRegion | None = None
    # Boards import internship titles only unless the owner asks for everything (ADR-010).
    scope: SourceScope = SourceScope.INTERNSHIPS_ONLY


class SourceUpdate(BaseModel):
    """The name, the enabled flag, and the scope change. The provider identifier never does.
    Omitting `scope` keeps it; the built-in feed's scope is always `all`."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    enabled: bool
    scope: SourceScope | None = None


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
    # Provider items excluded by the source's scope; normalized_count counts the admitted ones.
    filtered_count: int
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
    scope: SourceScope
    builtin: bool
    last_attempted_at: datetime | None
    last_success_at: datetime | None
    latest_run: RunResponse | None = None
    # Derived health (ADR-012 §11), never stored; set by app.services.sources.to_response.
    health: Literal["never_run", "healthy", "warning", "stale", "failing", "disabled"] = "never_run"
    consecutive_failures: int = 0
    last_success_age_hours: float | None = None
