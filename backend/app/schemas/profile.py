import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.enums import EducationLevel, RemotePreference
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


# --- Match Profile (ADR-010 §5): fit inputs only, never eligibility --------------------------


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
CourseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Terms = Annotated[list[Term], AfterValidator(_unique)]


class MatchItem(BaseModel):
    """A project, research item, activity, or experience."""

    model_config = ConfigDict(extra="forbid")

    name: CourseName
    description: Annotated[Annotated[str, Field(max_length=2_000)] | None, BlankToNone] = None


class MatchProfile(BaseModel):
    """The Match Profile, saved atomically by one PUT. Manual facts plus fit preferences."""

    model_config = ConfigDict(extra="forbid")

    skills: Annotated[Terms, Field(max_length=50)] = Field(default_factory=list[str])
    courses: Annotated[list[CourseName], AfterValidator(_unique), Field(max_length=50)] = Field(
        default_factory=list[str]
    )
    projects: list[MatchItem] = Field(default_factory=list[MatchItem], max_length=25)
    research: list[MatchItem] = Field(default_factory=list[MatchItem], max_length=25)
    activities: list[MatchItem] = Field(default_factory=list[MatchItem], max_length=25)
    experience: list[MatchItem] = Field(default_factory=list[MatchItem], max_length=25)
    interests: Annotated[Terms, Field(max_length=30)] = Field(default_factory=list[str])
    preferred_locations: Annotated[Terms, Field(max_length=20)] = Field(default_factory=list[str])
    remote_preference: RemotePreference | None = None
    availability_start: date | None = None
    availability_end: date | None = None

    # Mirrors ck_profiles_availability_end_not_before_start.
    @model_validator(mode="after")
    def _availability(self) -> Self:
        if (
            self.availability_start
            and self.availability_end
            and self.availability_end < self.availability_start
        ):
            raise ValueError("availability_end can't be before availability_start")
        return self


class MatchProfileSaveResponse(BaseModel):
    match_profile: MatchProfile
    # The single catalog pass: new evaluation rows, and opportunities whose inputs didn't change.
    evaluated_opportunities: int
    unchanged_opportunities: int
