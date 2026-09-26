"""Eligibility rules v1. All profile data and dates are synthetic."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.enums import (
    EducationLevel,
    EligibilityStatus,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.opportunities.eligibility import (
    RULES_VERSION,
    depends_on_projection,
    evaluate_eligibility,
)
from app.opportunities.eligibility.rules import age_on, evaluate_requirement
from app.opportunities.eligibility.schemas import (
    OpportunityInput,
    ProfileInput,
    RequirementInput,
    RuleResult,
)

ELIGIBLE = EligibilityStatus.ELIGIBLE
INELIGIBLE = EligibilityStatus.INELIGIBLE
NEEDS_VERIFICATION = EligibilityStatus.NEEDS_VERIFICATION

UNASSESSED = RequirementsAssessmentStatus.UNASSESSED
PARTIAL = RequirementsAssessmentStatus.PARTIAL
COMPLETE = RequirementsAssessmentStatus.COMPLETE

# A fictional high-school student: graduates 2041-06-10, starts college 2041-08-25.
PROFILE = ProfileInput(
    current_education_level=EducationLevel.HIGH_SCHOOL,
    education_status_as_of=date(2040, 9, 1),
    expected_graduation_date=date(2041, 6, 10),
    expected_enrollment_date=date(2041, 8, 25),
    expected_future_education_level=EducationLevel.UNDERGRADUATE,
    date_of_birth=date(2023, 6, 20),
)


def opportunity(
    start: date | None = None,
    deadline: date | None = None,
    assessment: RequirementsAssessmentStatus = COMPLETE,
) -> OpportunityInput:
    # Complete by default so composite tests exercise the requirement rules themselves.
    return OpportunityInput(
        start_date=start, application_deadline=deadline, requirements_assessment_status=assessment
    )


def requirement(
    requirement_type: RequirementType,
    value: dict[str, Any],
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START,
    reference_date: date | None = None,
) -> RequirementInput:
    return RequirementInput(
        requirement_type=requirement_type,
        value=value,
        applies_at=applies_at,
        reference_date=reference_date,
    )


def check(
    req: RequirementInput,
    opp: OpportunityInput,
    profile: ProfileInput = PROFILE,
) -> RuleResult:
    return evaluate_requirement(profile, opp, req)


# --- ELIG-AGE-001 ------------------------------------------------------------------------------

MIN_18 = requirement(RequirementType.MINIMUM_AGE, {"years": 18})


@pytest.mark.parametrize(
    ("start", "status", "age"),
    [
        (date(2041, 6, 19), INELIGIBLE, 17),  # one day before the 18th birthday
        (date(2041, 6, 20), ELIGIBLE, 18),  # exactly the minimum age
        (date(2041, 6, 21), ELIGIBLE, 18),  # one day after
    ],
)
def test_age_boundary_on_birthday(start: date, status: EligibilityStatus, age: int) -> None:
    result = check(MIN_18, opportunity(start=start))

    assert result.rule_id == "ELIG-AGE-001"
    assert result.status is status
    assert result.reference_date == start
    assert result.details == {"minimum_age": 18, "age": age}


def test_age_ineligible_reason_uses_documented_format() -> None:
    result = check(MIN_18, opportunity(start=date(2041, 6, 19)))

    assert result.reason == "Minimum age 18 exceeds user age 17 on 2041-06-19."


def test_age_is_not_computed_from_years_alone() -> None:
    # 2041 - 2023 = 18, but the birthday hasn't happened yet on 1 January.
    assert age_on(date(2023, 6, 20), date(2041, 1, 1)) == 17


def test_leap_day_birthday_is_reached_on_1_march() -> None:
    birth = date(2024, 2, 29)

    assert age_on(birth, date(2041, 2, 28)) == 16
    assert age_on(birth, date(2041, 3, 1)) == 17
    assert age_on(birth, date(2044, 2, 29)) == 20


def test_missing_birth_date_needs_verification() -> None:
    profile = PROFILE.model_copy(update={"date_of_birth": None})

    result = check(MIN_18, opportunity(start=date(2041, 7, 1)), profile)

    assert result.status is NEEDS_VERIFICATION
    assert "no date of birth" in result.reason


def test_missing_reference_date_needs_verification() -> None:
    result = check(MIN_18, opportunity(start=None))

    assert result.status is NEEDS_VERIFICATION
    assert result.reference_date is None
    assert "program_start date, which is unknown" in result.reason


def test_age_uses_explicit_date_when_the_posting_states_one() -> None:
    req = requirement(
        RequirementType.MINIMUM_AGE,
        {"years": 18},
        RequirementAppliesAt.EXPLICIT_DATE,
        reference_date=date(2041, 6, 1),
    )

    result = check(req, opportunity(start=date(2041, 7, 1)))

    assert result.status is INELIGIBLE
    assert result.reference_date == date(2041, 6, 1)


# --- ELIG-EDU-001 ------------------------------------------------------------------------------

UNDERGRAD_OR_INCOMING = {"levels": ["undergraduate"], "accepts_incoming": True}
ENROLLED_UNDERGRAD = {"levels": ["undergraduate"]}


def test_high_school_student_is_eligible_for_incoming_undergraduate_program() -> None:
    req = requirement(RequirementType.EDUCATION, UNDERGRAD_OR_INCOMING)

    result = check(req, opportunity(start=date(2041, 6, 20)))

    assert result.rule_id == "ELIG-EDU-001"
    assert result.status is ELIGIBLE
    assert result.depends_on_projected_status
    assert "projected status is incoming undergraduate" in result.reason
    assert "expected, not actual" in result.reason


def test_college_enrollment_required_at_application_before_graduation_is_ineligible() -> None:
    req = requirement(
        RequirementType.EDUCATION, ENROLLED_UNDERGRAD, RequirementAppliesAt.APPLICATION
    )

    result = check(req, opportunity(start=date(2041, 9, 1), deadline=date(2041, 1, 15)))

    assert result.status is INELIGIBLE
    assert result.reference_date == date(2041, 1, 15)
    assert not result.depends_on_projected_status
    assert "current status is enrolled high_school" in result.reason


@pytest.mark.parametrize(
    ("start", "status"),
    [
        (date(2041, 8, 24), INELIGIBLE),  # graduated, not yet enrolled
        (date(2041, 8, 25), ELIGIBLE),  # enrolled on the enrollment date
    ],
)
def test_enrolled_requirement_across_enrollment_date(
    start: date, status: EligibilityStatus
) -> None:
    result = check(requirement(RequirementType.EDUCATION, ENROLLED_UNDERGRAD), opportunity(start))

    assert result.status is status
    assert result.depends_on_projected_status


@pytest.mark.parametrize(
    ("start", "status"),
    [
        (date(2041, 6, 9), ELIGIBLE),  # still in high school the day before graduation
        (date(2041, 6, 10), INELIGIBLE),  # graduated
    ],
)
def test_high_school_requirement_across_graduation(start: date, status: EligibilityStatus) -> None:
    req = requirement(RequirementType.EDUCATION, {"levels": ["high_school"]})

    assert check(req, opportunity(start)).status is status


def test_missing_opportunity_start_date_needs_verification() -> None:
    req = requirement(RequirementType.EDUCATION, UNDERGRAD_OR_INCOMING)

    result = check(req, opportunity(start=None))

    assert result.status is NEEDS_VERIFICATION
    assert result.reference_date is None


@pytest.mark.parametrize(
    "missing", ["expected_graduation_date", "expected_enrollment_date", "education_status_as_of"]
)
def test_missing_profile_transition_needs_verification(missing: str) -> None:
    changes: dict[str, object] = {missing: None}
    if missing == "education_status_as_of":
        changes["current_education_level"] = None
    profile = PROFILE.model_copy(update=changes)
    req = requirement(RequirementType.EDUCATION, UNDERGRAD_OR_INCOMING)

    result = check(req, opportunity(start=date(2041, 7, 1)), profile)

    assert result.status is NEEDS_VERIFICATION
    assert "can't be determined" in result.reason
    assert result.details is not None and result.details["phase"] == "unknown"


# --- ELIG-CIT-001 ------------------------------------------------------------------------------

US_ONLY = requirement(RequirementType.CITIZENSHIP, {"countries": ["US"]})


@pytest.mark.parametrize("citizenships", [None, []])
def test_unknown_citizenship_needs_verification(citizenships: list[str] | None) -> None:
    profile = PROFILE.model_copy(update={"citizenships": citizenships})

    result = check(US_ONLY, opportunity(), profile)

    assert result.rule_id == "ELIG-CIT-001"
    assert result.status is NEEDS_VERIFICATION
    assert result.reason == "Citizenship requirement US cannot be confirmed from profile."


@pytest.mark.parametrize(
    ("citizenships", "status"),
    [(["US"], ELIGIBLE), (["CA", "US"], ELIGIBLE), (["CA"], INELIGIBLE)],
)
def test_explicit_citizenship_is_matched(
    citizenships: list[str], status: EligibilityStatus
) -> None:
    profile = PROFILE.model_copy(update={"citizenships": citizenships})

    assert check(US_ONLY, opportunity(), profile).status is status


def test_profile_citizenship_must_be_country_codes() -> None:
    with pytest.raises(ValidationError):
        ProfileInput(citizenships=["United States"])


# --- Requirements the v1 rules can't evaluate ---------------------------------------------------


def test_unsupported_requirement_type_needs_verification() -> None:
    req = requirement(RequirementType.WORK_AUTHORIZATION, {"countries": ["US"]})

    result = check(req, opportunity())

    assert result.rule_id == "ELIG-REQ-001"
    assert result.status is NEEDS_VERIFICATION


@pytest.mark.parametrize(
    ("requirement_type", "value"),
    [
        (RequirementType.MINIMUM_AGE, {"years": "eighteen"}),
        (RequirementType.EDUCATION, {"levels": []}),
        (RequirementType.CITIZENSHIP, {"countries": ["usa"]}),
    ],
)
def test_malformed_requirement_value_needs_verification(
    requirement_type: RequirementType, value: dict[str, Any]
) -> None:
    result = check(requirement(requirement_type, value), opportunity(start=date(2041, 7, 1)))

    assert result.rule_id == "ELIG-REQ-001"
    assert result.status is NEEDS_VERIFICATION


# --- Composite evaluator -----------------------------------------------------------------------

EDU = requirement(RequirementType.EDUCATION, UNDERGRAD_OR_INCOMING)


def test_requirements_are_unassessed_by_default() -> None:
    assert OpportunityInput().requirements_assessment_status is UNASSESSED


@pytest.mark.parametrize(
    ("assessment", "status"),
    [(UNASSESSED, NEEDS_VERIFICATION), (PARTIAL, NEEDS_VERIFICATION), (COMPLETE, ELIGIBLE)],
)
def test_no_requirements_depends_on_assessment(
    assessment: RequirementsAssessmentStatus, status: EligibilityStatus
) -> None:
    evaluation = evaluate_eligibility(PROFILE, opportunity(assessment=assessment), [])

    assert evaluation.status is status
    assert evaluation.rules_version == RULES_VERSION == "v1"
    [result] = evaluation.rule_results
    assert result.rule_id == "ELIG-REQ-000"
    assert result.status is status
    assert result.requirement_id is None
    assert result.details == {"requirements_assessment_status": assessment.value}


def test_unassessed_reason_explains_the_missing_assessment() -> None:
    evaluation = evaluate_eligibility(PROFILE, opportunity(assessment=UNASSESSED), [])

    assert evaluation.reasons == [
        "ELIG-REQ-000: The opportunity's hard eligibility requirements haven't been assessed"
        " yet, so eligibility can't be confirmed."
    ]


US_CITIZEN = PROFILE.model_copy(update={"citizenships": ["US"]})


@pytest.mark.parametrize(
    ("requirements", "start", "profile", "status"),
    [
        ([MIN_18], date(2041, 6, 20), PROFILE, NEEDS_VERIFICATION),  # known age passes
        ([MIN_18, EDU], date(2041, 6, 20), PROFILE, NEEDS_VERIFICATION),  # age + education pass
        ([MIN_18], date(2041, 6, 19), PROFILE, INELIGIBLE),  # explicit failure is definitive
        (
            [MIN_18, US_ONLY],
            date(2041, 6, 20),
            PROFILE.model_copy(update={"citizenships": ["CA"]}),
            INELIGIBLE,
        ),  # known citizenship mismatch
    ],
)
def test_partial_assessment(
    requirements: list[RequirementInput],
    start: date,
    profile: ProfileInput,
    status: EligibilityStatus,
) -> None:
    evaluation = evaluate_eligibility(profile, opportunity(start, assessment=PARTIAL), requirements)

    assert evaluation.status is status
    assert evaluation.rule_results[0].rule_id == "ELIG-REQ-000"
    assert evaluation.rule_results[0].status is NEEDS_VERIFICATION
    assert len(evaluation.rule_results) == 1 + len(requirements)


def test_partial_assessment_is_not_flagged_as_projected() -> None:
    # Education passes on a projection, but the final needs_verification comes from ELIG-REQ-000.
    evaluation = evaluate_eligibility(
        US_CITIZEN, opportunity(date(2041, 6, 20), assessment=PARTIAL), [EDU]
    )

    assert evaluation.status is NEEDS_VERIFICATION
    assert not evaluation.depends_on_projected_status


def test_unassessed_still_reports_an_explicit_failure() -> None:
    evaluation = evaluate_eligibility(
        PROFILE, opportunity(date(2041, 6, 19), assessment=UNASSESSED), [MIN_18]
    )

    assert evaluation.status is INELIGIBLE


@pytest.mark.parametrize(
    ("start", "citizenships", "status"),
    [
        (date(2041, 6, 20), ["US"], ELIGIBLE),  # eligible + eligible + eligible
        (date(2041, 6, 20), None, NEEDS_VERIFICATION),  # needs_verification beats eligible
        (date(2041, 6, 19), None, INELIGIBLE),  # ineligible beats needs_verification
    ],
)
def test_precedence(start: date, citizenships: list[str] | None, status: EligibilityStatus) -> None:
    profile = PROFILE.model_copy(update={"citizenships": citizenships})

    evaluation = evaluate_eligibility(profile, opportunity(start), [MIN_18, EDU, US_ONLY])

    assert evaluation.status is status
    assert [r.rule_id for r in evaluation.rule_results] == [
        "ELIG-REQ-000",
        "ELIG-AGE-001",
        "ELIG-EDU-001",
        "ELIG-CIT-001",
    ]
    assert len(evaluation.reasons) == 4


def test_eligible_result_that_relies_on_projection_is_flagged() -> None:
    profile = PROFILE.model_copy(update={"citizenships": ["US"]})

    evaluation = evaluate_eligibility(profile, opportunity(date(2041, 6, 20)), [MIN_18, EDU])

    assert evaluation.status is ELIGIBLE
    assert evaluation.depends_on_projected_status
    assert any("projected" in reason for reason in evaluation.reasons)


def test_projection_flag_ignores_results_that_did_not_decide_the_status() -> None:
    # Ineligible on age alone; the projected education result doesn't change that.
    evaluation = evaluate_eligibility(PROFILE, opportunity(date(2041, 6, 19)), [MIN_18, EDU])

    assert evaluation.status is INELIGIBLE
    assert not evaluation.depends_on_projected_status


# Graduated 2041-06-10 but not enrolled until 2041-08-25: a projected education mismatch.
ENROLLED_EDU = requirement(RequirementType.EDUCATION, ENROLLED_UNDERGRAD)


def test_ineligible_only_from_projected_mismatch_is_flagged() -> None:
    evaluation = evaluate_eligibility(
        US_CITIZEN, opportunity(date(2041, 8, 24)), [MIN_18, ENROLLED_EDU, US_ONLY]
    )

    assert evaluation.status is INELIGIBLE
    assert [r.status for r in evaluation.rule_results] == [ELIGIBLE, ELIGIBLE, INELIGIBLE, ELIGIBLE]
    assert evaluation.depends_on_projected_status


def test_ineligible_with_independent_non_projected_failure_is_not_flagged() -> None:
    profile = PROFILE.model_copy(update={"citizenships": ["CA"]})

    evaluation = evaluate_eligibility(
        profile, opportunity(date(2041, 8, 24)), [MIN_18, ENROLLED_EDU, US_ONLY]
    )

    assert evaluation.status is INELIGIBLE
    edu, cit = evaluation.rule_results[2], evaluation.rule_results[3]
    assert edu.status is INELIGIBLE and edu.depends_on_projected_status
    assert cit.status is INELIGIBLE and not cit.depends_on_projected_status
    assert not evaluation.depends_on_projected_status


def _result(status: EligibilityStatus, projected: bool) -> RuleResult:
    return RuleResult(
        rule_id="ELIG-TEST",
        status=status,
        reason="synthetic",
        depends_on_projected_status=projected,
    )


@pytest.mark.parametrize(
    ("status", "results", "expected"),
    [
        # A non-projected needs_verification (e.g. partial assessment) stands on its own.
        (
            NEEDS_VERIFICATION,
            [(NEEDS_VERIFICATION, False), (NEEDS_VERIFICATION, True), (ELIGIBLE, True)],
            False,
        ),
        # Every needs_verification result relies on projection.
        (NEEDS_VERIFICATION, [(ELIGIBLE, False), (NEEDS_VERIFICATION, True)], True),
        # Eligible: any projected pass is load-bearing.
        (ELIGIBLE, [(ELIGIBLE, False), (ELIGIBLE, True)], True),
        (ELIGIBLE, [(ELIGIBLE, False)], False),
    ],
)
def test_projection_dependency_aggregation(
    status: EligibilityStatus, results: list[tuple[EligibilityStatus, bool]], expected: bool
) -> None:
    rule_results = [_result(s, p) for s, p in results]

    assert depends_on_projection(status, rule_results) is expected


def test_evaluation_is_deterministic() -> None:
    args = (PROFILE, opportunity(date(2041, 6, 20)), [MIN_18, EDU, US_ONLY])

    assert evaluate_eligibility(*args) == evaluate_eligibility(*args)
