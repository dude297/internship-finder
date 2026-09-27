import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import EducationLevel
from app.schemas.common import BlankToNone, CountryList


class ProfileBody(BaseModel):
    """The canonical, eligibility-relevant profile. Every field is optional; missing values make
    the affected rules `needs_verification`, never a guess."""

    model_config = ConfigDict(extra="forbid")

    current_education_level: EducationLevel | None = None
    current_grade: Annotated[Annotated[str, Field(max_length=32)] | None, BlankToNone] = None
    education_status_as_of: date | None = None
    expected_graduation_date: date | None = None
    expected_enrollment_date: date | None = None
    expected_future_education_level: EducationLevel | None = None
    date_of_birth: date | None = None
    citizenships: CountryList = None
    work_authorizations: CountryList = None
    location: Annotated[Annotated[str, Field(max_length=200)] | None, BlankToNone] = None

    # Mirrors the database CHECK constraints so clients get a 422, not a conflict.
    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.current_education_level is None) != (self.education_status_as_of is None):
            raise ValueError(
                "current_education_level and education_status_as_of must be set together"
            )
        if (
            self.expected_enrollment_date
            and self.expected_graduation_date
            and self.expected_enrollment_date < self.expected_graduation_date
        ):
            raise ValueError("expected_enrollment_date can't be before expected_graduation_date")
        if (
            self.expected_graduation_date
            and self.education_status_as_of
            and self.expected_graduation_date <= self.education_status_as_of
        ):
            raise ValueError("expected_graduation_date must be after education_status_as_of")
        if self.date_of_birth and self.date_of_birth > datetime.now(UTC).date():
            raise ValueError("date_of_birth can't be in the future")
        return self


class ProfileResponse(ProfileBody):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    updated_at: datetime


class ProfileSaveResponse(BaseModel):
    profile: ProfileResponse
    # Opportunities re-evaluated because an eligibility-relevant field changed.
    reevaluated_opportunities: int
