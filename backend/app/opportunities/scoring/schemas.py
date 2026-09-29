"""Inputs and outputs of fit scoring. Distinct from ORM models and API schemas."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import RemoteMode, RemotePreference, RequirementsAssessmentStatus


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NamedItem(_Frozen):
    """A project or research fact value."""

    name: str
    description: str | None = None


class FitProfileInput(_Frozen):
    """Everything about the owner that fit v1 reads (ADR-010 §5), in stored order. Activities
    and experience aren't here: they don't score in v1."""

    skills: tuple[str, ...] = ()
    courses: tuple[str, ...] = ()
    projects: tuple[NamedItem, ...] = ()
    research: tuple[NamedItem, ...] = ()
    interests: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    remote_preference: RemotePreference | None = None
    availability_start: date | None = None
    availability_end: date | None = None


class FitOpportunityInput(BaseModel):
    """The posting fields fit v1 reads. Built from the ORM row (from_attributes)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    title: str
    organization: str
    description: str | None = None
    location: str | None = None
    remote_mode: RemoteMode | None = None
    application_deadline: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    posted_at: datetime | None = None
    application_url: str | None = None
    requirements_assessment_status: RequirementsAssessmentStatus = (
        RequirementsAssessmentStatus.UNASSESSED
    )


MissingInput = Literal["profile", "opportunity"]


class ComponentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    weight: int
    # True when there wasn't enough evidence to evaluate: the score is 0, not a guess.
    missing: bool = False
    missing_input: MissingInput | None = None
    reason: str
    matched: list[str] = Field(default_factory=list[str])
    unmatched: list[str] = Field(default_factory=list[str])
    details: dict[str, Any] | None = None


class ScoreBreakdown(BaseModel):
    """Stored in opportunity_evaluations.score_breakdown (JSON). Plain data, never HTML."""

    model_config = ConfigDict(frozen=True)

    scoring_version: str
    score: int = Field(ge=0, le=100)
    # Sum of the weights of the evaluated (non-missing) components.
    coverage: int = Field(ge=0, le=100)
    components: dict[str, ComponentResult]
