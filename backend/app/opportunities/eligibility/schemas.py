"""Domain inputs/outputs of the eligibility engine. Distinct from ORM models and API schemas.

Inputs are built from ORM rows with `Model.model_validate(orm_obj)` (from_attributes).
"""

import uuid
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.enums import (
    EducationLevel,
    EligibilityStatus,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.profile.education import EducationTimeline

# ISO 3166-1 alpha-2, uppercase.
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class ProfileInput(EducationTimeline):
    """Canonical profile fields used by hard eligibility. Never built from profile facts."""

    date_of_birth: date | None = None
    citizenships: list[CountryCode] | None = None


class OpportunityInput(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    application_deadline: date | None = None
    start_date: date | None = None
    requirements_assessment_status: RequirementsAssessmentStatus = (
        RequirementsAssessmentStatus.UNASSESSED
    )


class RequirementInput(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID | None = None
    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START
    reference_date: date | None = None


# Shapes of OpportunityRequirement.value per requirement type.


class _Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MinimumAgeValue(_Value):
    years: int = Field(ge=0, le=120)


class EducationValue(_Value):
    """Accepted levels. `accepts_incoming` also accepts users who finished the previous level
    and are about to start an accepted one (e.g. "incoming undergraduates")."""

    levels: list[EducationLevel] = Field(min_length=1)
    accepts_incoming: bool = False


class CitizenshipValue(_Value):
    """Citizenship of at least one of `countries` is required."""

    countries: list[CountryCode] = Field(min_length=1)


REQUIREMENT_VALUE_SCHEMAS: dict[RequirementType, type[_Value]] = {
    RequirementType.MINIMUM_AGE: MinimumAgeValue,
    RequirementType.EDUCATION: EducationValue,
    RequirementType.CITIZENSHIP: CitizenshipValue,
}


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    status: EligibilityStatus
    reason: str
    requirement_id: uuid.UUID | None = None
    reference_date: date | None = None
    depends_on_projected_status: bool = False
    details: dict[str, Any] | None = None


class EligibilityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: EligibilityStatus
    rules_version: str
    # True when the final status relies on an expected (not yet actual) education transition.
    depends_on_projected_status: bool
    rule_results: tuple[RuleResult, ...]

    @property
    def reasons(self) -> list[str]:
        return [f"{r.rule_id}: {r.reason}" for r in self.rule_results]
