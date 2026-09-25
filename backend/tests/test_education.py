"""Temporal education projection. All dates are fictional."""

from datetime import date

import pytest

from app.enums import EducationLevel, EducationPhase
from app.profile.education import EducationTimeline, resolve_education_status

HS = EducationLevel.HIGH_SCHOOL
UG = EducationLevel.UNDERGRADUATE

AS_OF = date(2040, 9, 1)
GRADUATION = date(2041, 6, 10)
ENROLLMENT = date(2041, 8, 25)

TIMELINE = EducationTimeline(
    current_education_level=HS,
    education_status_as_of=AS_OF,
    expected_graduation_date=GRADUATION,
    expected_enrollment_date=ENROLLMENT,
    expected_future_education_level=UG,
)


@pytest.mark.parametrize(
    ("reference", "phase", "level", "projected"),
    [
        (AS_OF, EducationPhase.ENROLLED, HS, False),
        (date(2041, 6, 9), EducationPhase.ENROLLED, HS, False),  # day before graduation
        (GRADUATION, EducationPhase.INCOMING, UG, True),  # graduated on the day itself
        (date(2041, 8, 24), EducationPhase.INCOMING, UG, True),  # day before enrollment
        (ENROLLMENT, EducationPhase.ENROLLED, UG, True),
        (date(2042, 3, 1), EducationPhase.ENROLLED, UG, True),
    ],
)
def test_projects_status_across_graduation_and_enrollment(
    reference: date, phase: EducationPhase, level: EducationLevel, projected: bool
) -> None:
    result = resolve_education_status(TIMELINE, reference)

    assert (result.phase, result.level, result.projected) == (phase, level, projected)
    assert not result.insufficient


def test_projected_explanation_names_the_expected_dates() -> None:
    result = resolve_education_status(TIMELINE, date(2041, 7, 1))

    assert "2041-06-10" in result.explanation
    assert "2041-08-25" in result.explanation
    assert result.describe() == "incoming undergraduate"


@pytest.mark.parametrize(
    ("changes", "reference"),
    [
        ({"current_education_level": None, "education_status_as_of": None}, AS_OF),
        ({"expected_graduation_date": None}, date(2040, 12, 1)),
        ({"expected_enrollment_date": None}, GRADUATION),
        ({"expected_future_education_level": None}, date(2041, 9, 1)),
        # Can't project backwards from the date the status was recorded.
        ({}, date(2040, 8, 31)),
        # Contradictory timeline (the database forbids it, the resolver doesn't guess either).
        ({"expected_enrollment_date": date(2041, 1, 1)}, GRADUATION),
    ],
)
def test_insufficient_information_is_unknown_not_a_guess(
    changes: dict[str, object], reference: date
) -> None:
    timeline = TIMELINE.model_copy(update=changes)

    result = resolve_education_status(timeline, reference)

    assert result.insufficient
    assert result.phase is EducationPhase.UNKNOWN
    assert result.level is None
    assert result.describe() == "unknown"
    assert result.explanation


def test_missing_future_plan_does_not_matter_before_graduation() -> None:
    timeline = TIMELINE.model_copy(
        update={"expected_enrollment_date": None, "expected_future_education_level": None}
    )

    result = resolve_education_status(timeline, date(2041, 1, 15))

    assert (result.phase, result.level) == (EducationPhase.ENROLLED, HS)


def test_without_graduation_date_only_the_recorded_date_is_known() -> None:
    timeline = TIMELINE.model_copy(update={"expected_graduation_date": None})

    assert resolve_education_status(timeline, AS_OF).level is HS
    assert resolve_education_status(timeline, date(2040, 9, 2)).insufficient
