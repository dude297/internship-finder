import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.enums import (
    ApplicationStatus,
    EligibilityStatus,
    ExtractionMethod,
    OpportunitySourceType,
    OpportunityType,
    RemoteMode,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.opportunities.eligibility.schemas import REQUIREMENT_VALUE_SCHEMAS
from app.opportunities.scoring import ScoreBreakdown
from app.schemas.application import ApplicationResponse
from app.schemas.common import BlankToNone, CountryCode

_countries = TypeAdapter(list[CountryCode])

# Only http(s) links: the UI renders this as a link, so `javascript:` and friends are rejected.
HttpUrl = Annotated[str, Field(max_length=2048, pattern=r"^https?://[^\s]+$")]


class RequirementBody(BaseModel):
    """One structured hard requirement (the Milestone 1 representation, ADR-006 §3).

    `value` is validated against the per-type schema for the types eligibility v1 evaluates.
    `work_authorization` and `other` are stored as free-form objects (UI: {"description": ...})
    and always evaluate to needs_verification (ELIG-REQ-001)."""

    model_config = ConfigDict(extra="forbid")

    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START
    reference_date: date | None = None
    source_text: Annotated[Annotated[str, Field(max_length=5_000)] | None, BlankToNone] = None

    @model_validator(mode="after")
    def _valid(self) -> Self:
        schema = REQUIREMENT_VALUE_SCHEMAS.get(self.requirement_type)
        if schema is not None:
            value = dict(self.value)
            if self.requirement_type is RequirementType.CITIZENSHIP:
                value["countries"] = _countries.validate_python(value.get("countries"))
            self.value = schema.model_validate(value).model_dump(mode="json")
        if (self.applies_at is RequirementAppliesAt.EXPLICIT_DATE) != (
            self.reference_date is not None
        ):
            raise ValueError("reference_date is required exactly when applies_at is explicit_date")
        return self


# Response models declare plain fields instead of inheriting the request validators, so a stored
# row written by another path (a future parser) can always be read back.


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt
    reference_date: date | None
    source_text: str | None
    extraction_method: ExtractionMethod
    extractor_name: str | None
    extractor_version: str | None


class OpportunityFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    organization: str = Field(min_length=1, max_length=200)
    description: Annotated[Annotated[str, Field(max_length=50_000)] | None, BlankToNone] = None
    opportunity_type: OpportunityType
    application_url: Annotated[HttpUrl | None, BlankToNone] = None
    location: Annotated[Annotated[str, Field(max_length=200)] | None, BlankToNone] = None
    remote_mode: RemoteMode | None = None
    application_deadline: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    requirements_assessment_status: RequirementsAssessmentStatus = (
        RequirementsAssessmentStatus.UNASSESSED
    )

    @model_validator(mode="after")
    def _dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date can't be before start_date")
        return self


class OpportunityBody(OpportunityFields):
    """Create/replace request. `requirements` is the complete set: an update replaces it."""

    requirements: list[RequirementBody] = Field(
        default_factory=list[RequirementBody], max_length=50
    )


class RuleResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    requirement_id: uuid.UUID | None
    status: EligibilityStatus
    reason: str
    reference_date: date | None
    depends_on_projected_status: bool
    details: dict[str, Any] | None


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    eligibility_status: EligibilityStatus
    eligibility_rules_version: str
    depends_on_projected_status: bool
    evaluated_at: datetime
    rule_results: list[RuleResultResponse]
    # Fit (ADR-010). Null on evaluations from before scoring v1.
    fit_score: int | None = None
    scoring_version: str | None = None
    score_breakdown: ScoreBreakdown | None = None


# imported: at least one automated source record; manual: manual provenance only.
Origin = Literal["imported", "manual"]
# open: an automated record is active; closed: automated records exist, none active;
# manual: managed by hand (no automated records).
Availability = Literal["open", "closed", "manual"]


class FitComponentSummary(BaseModel):
    score: int
    weight: int
    missing: bool


class OpportunitySummary(BaseModel):
    id: uuid.UUID
    title: str
    organization: str
    opportunity_type: OpportunityType
    location: str | None
    remote_mode: RemoteMode | None
    application_deadline: date | None
    start_date: date | None
    posted_at: datetime | None
    first_seen_at: datetime
    requirements_assessment_status: RequirementsAssessmentStatus
    eligibility_status: EligibilityStatus | None
    evaluated_at: datetime | None
    # From the current evaluation; null when it has no fit (no profile, or before scoring v1).
    fit_score: int | None = None
    scoring_version: str | None = None
    fit_coverage: int | None = None
    fit_components: dict[str, FitComponentSummary] | None = None
    application_status: ApplicationStatus | None
    origin: Origin
    availability: Availability
    source_names: list[str]
    # ADR-012 §8: one aggregate subquery, never per-row.
    pending_requirement_count: int = 0
    requirements_stale: bool = False


class OpportunityPage(BaseModel):
    items: list[OpportunitySummary]
    total: int
    limit: int
    offset: int


class SourceRecordResponse(BaseModel):
    """Safe provenance for display. The raw payload is never sent to the browser."""

    source_name: str
    source_type: OpportunitySourceType
    automated: bool
    is_active: bool
    closed_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    source_url: str | None
    source_published_at: datetime | None
    source_updated_at: datetime | None


class OpportunityDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    organization: str
    description: str | None
    opportunity_type: OpportunityType
    application_url: str | None
    location: str | None
    remote_mode: RemoteMode | None
    application_deadline: date | None
    start_date: date | None
    end_date: date | None
    requirements_assessment_status: RequirementsAssessmentStatus
    created_at: datetime
    updated_at: datetime
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    manually_curated_at: datetime | None
    # ADR-012 §6: set when a source update changed the posting text after review; cleared by the
    # owner's next review batch.
    requirements_stale_since: datetime | None = None
    # Pending requirement candidates for this opportunity (ADR-012 §8).
    pending_requirement_count: int = 0
    requirements: list[RequirementResponse]
    application: ApplicationResponse | None
    origin: Origin = "manual"
    availability: Availability = "manual"
    sources: list[SourceRecordResponse] = Field(default_factory=list[SourceRecordResponse])
    # Null when there is no profile yet: eligibility is never faked.
    latest_evaluation: EvaluationResponse | None = None
    profile_exists: bool = False
