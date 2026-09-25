"""Time-aware education status (ADR-005): project the canonical profile to a reference date.

Pure and deterministic. Transitions happen *on* their date: on the expected graduation date the
user has graduated; on the expected enrollment date they are enrolled at the future level.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from app.enums import EducationLevel, EducationPhase


class EducationTimeline(BaseModel):
    """The canonical profile's education fields. Build from an ORM Profile with model_validate."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    current_education_level: EducationLevel | None = None
    education_status_as_of: date | None = None
    expected_graduation_date: date | None = None
    expected_enrollment_date: date | None = None
    expected_future_education_level: EducationLevel | None = None


class EducationStatusResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference_date: date
    phase: EducationPhase
    level: EducationLevel | None
    # True when an expected (not yet actual) graduation/enrollment was applied to get here.
    projected: bool
    explanation: str

    @property
    def insufficient(self) -> bool:
        return self.phase is EducationPhase.UNKNOWN

    def describe(self) -> str:
        if self.level is None:  # only when UNKNOWN
            return "unknown"
        return f"{self.phase.value} {self.level.value}"


def _unknown(reference_date: date, why: str) -> EducationStatusResult:
    return EducationStatusResult(
        reference_date=reference_date,
        phase=EducationPhase.UNKNOWN,
        level=None,
        projected=False,
        explanation=why,
    )


def resolve_education_status(
    timeline: EducationTimeline, reference_date: date
) -> EducationStatusResult:
    current = timeline.current_education_level
    as_of = timeline.education_status_as_of
    graduation = timeline.expected_graduation_date
    enrollment = timeline.expected_enrollment_date
    future = timeline.expected_future_education_level

    if current is None or as_of is None:
        return _unknown(reference_date, "The profile has no current education level.")
    if reference_date < as_of:
        return _unknown(
            reference_date,
            f"{reference_date} is before {as_of}, the date the education status was recorded.",
        )
    if graduation is None:
        if reference_date == as_of:
            return EducationStatusResult(
                reference_date=reference_date,
                phase=EducationPhase.ENROLLED,
                level=current,
                projected=False,
                explanation=f"Recorded as {current.value} on {as_of}.",
            )
        return _unknown(
            reference_date,
            f"No expected graduation date, so {current.value} status on {as_of}"
            f" can't be projected to {reference_date}.",
        )
    if reference_date < graduation:
        return EducationStatusResult(
            reference_date=reference_date,
            phase=EducationPhase.ENROLLED,
            level=current,
            projected=False,
            explanation=f"Still {current.value} on {reference_date}"
            f" (expected graduation {graduation}).",
        )
    # On or after expected graduation: the status depends on the expected next step.
    if future is None or enrollment is None:
        return _unknown(
            reference_date,
            f"Expected to finish {current.value} on {graduation}, but the profile has no"
            " expected future education level and enrollment date.",
        )
    if enrollment < graduation:
        return _unknown(reference_date, "Expected enrollment is before expected graduation.")
    if reference_date < enrollment:
        return EducationStatusResult(
            reference_date=reference_date,
            phase=EducationPhase.INCOMING,
            level=future,
            projected=True,
            explanation=f"Projected incoming {future.value} on {reference_date}: expected to"
            f" graduate {current.value} on {graduation} and enroll on {enrollment}.",
        )
    return EducationStatusResult(
        reference_date=reference_date,
        phase=EducationPhase.ENROLLED,
        level=future,
        projected=True,
        explanation=f"Projected enrolled {future.value} on {reference_date}: expected"
        f" enrollment on {enrollment}.",
    )
