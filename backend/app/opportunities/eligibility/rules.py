"""Eligibility rules v1 (docs/eligibility.md). Deterministic; each rule handles one requirement."""

from collections.abc import Callable
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.enums import (
    EducationPhase,
    EligibilityStatus,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.opportunities.eligibility.schemas import (
    REQUIREMENT_VALUE_SCHEMAS,
    CitizenshipValue,
    EducationValue,
    MinimumAgeValue,
    OpportunityInput,
    ProfileInput,
    RequirementInput,
    RuleResult,
)
from app.profile.education import resolve_education_status

RULES_VERSION = "v1"

ELIGIBLE = EligibilityStatus.ELIGIBLE
INELIGIBLE = EligibilityStatus.INELIGIBLE
NEEDS_VERIFICATION = EligibilityStatus.NEEDS_VERIFICATION

Rule = Callable[[ProfileInput, OpportunityInput, RequirementInput], RuleResult]


def reference_date_for(requirement: RequirementInput, opportunity: OpportunityInput) -> date | None:
    match requirement.applies_at:
        case RequirementAppliesAt.APPLICATION:
            return opportunity.application_deadline
        case RequirementAppliesAt.PROGRAM_START:
            return opportunity.start_date
        case RequirementAppliesAt.EXPLICIT_DATE:
            return requirement.reference_date


def _missing_reference(rule_id: str, requirement: RequirementInput, what: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=NEEDS_VERIFICATION,
        reason=f"{what} applies on the {requirement.applies_at.value} date, which is unknown.",
        requirement_id=requirement.id,
    )


def age_on(birth: date, on: date) -> int:
    """Completed years. A 29 February birthday is reached on 1 March in non-leap years."""
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def check_minimum_age(
    profile: ProfileInput, opportunity: OpportunityInput, requirement: RequirementInput
) -> RuleResult:
    rule_id = "ELIG-AGE-001"
    minimum = MinimumAgeValue.model_validate(requirement.value).years
    ref = reference_date_for(requirement, opportunity)
    if ref is None:
        return _missing_reference(rule_id, requirement, f"Minimum age {minimum}")
    if profile.date_of_birth is None:
        return RuleResult(
            rule_id=rule_id,
            status=NEEDS_VERIFICATION,
            reason=f"Minimum age {minimum} on {ref} can't be checked: the profile has no date"
            " of birth.",
            requirement_id=requirement.id,
            reference_date=ref,
        )
    age = age_on(profile.date_of_birth, ref)
    met = age >= minimum
    return RuleResult(
        rule_id=rule_id,
        status=ELIGIBLE if met else INELIGIBLE,
        reason=f"User age {age} on {ref} meets minimum age {minimum}."
        if met
        else f"Minimum age {minimum} exceeds user age {age} on {ref}.",
        requirement_id=requirement.id,
        reference_date=ref,
        details={"minimum_age": minimum, "age": age},
    )


def check_education(
    profile: ProfileInput, opportunity: OpportunityInput, requirement: RequirementInput
) -> RuleResult:
    rule_id = "ELIG-EDU-001"
    value = EducationValue.model_validate(requirement.value)
    required = " or ".join(level.value for level in value.levels)
    if value.accepts_incoming:
        required += " (incoming accepted)"
    ref = reference_date_for(requirement, opportunity)
    if ref is None:
        return _missing_reference(rule_id, requirement, f"Education requirement {required}")

    status = resolve_education_status(profile, ref)
    details: dict[str, Any] = {
        "required_levels": [level.value for level in value.levels],
        "accepts_incoming": value.accepts_incoming,
        "phase": status.phase.value,
        "level": status.level.value if status.level else None,
        "explanation": status.explanation,
    }
    if status.insufficient:
        return RuleResult(
            rule_id=rule_id,
            status=NEEDS_VERIFICATION,
            reason=f"Requires {required} status on {ref}; education status can't be determined."
            f" {status.explanation}",
            requirement_id=requirement.id,
            reference_date=ref,
            details=details,
        )

    accepted_phases = {EducationPhase.ENROLLED}
    if value.accepts_incoming:
        accepted_phases.add(EducationPhase.INCOMING)
    met = status.level in value.levels and status.phase in accepted_phases
    kind = "projected" if status.projected else "current"
    reason = f"Requires {required} status on {ref}; {kind} status is {status.describe()}."
    if status.projected:
        reason += f" This relies on expected, not actual, dates: {status.explanation}"
    return RuleResult(
        rule_id=rule_id,
        status=ELIGIBLE if met else INELIGIBLE,
        reason=reason,
        requirement_id=requirement.id,
        reference_date=ref,
        depends_on_projected_status=status.projected,
        details=details,
    )


def check_citizenship(
    profile: ProfileInput, opportunity: OpportunityInput, requirement: RequirementInput
) -> RuleResult:
    rule_id = "ELIG-CIT-001"
    required = CitizenshipValue.model_validate(requirement.value).countries
    required_text = " or ".join(required)
    if not profile.citizenships:
        return RuleResult(
            rule_id=rule_id,
            status=NEEDS_VERIFICATION,
            reason=f"Citizenship requirement {required_text} cannot be confirmed from profile.",
            requirement_id=requirement.id,
        )
    met = bool(set(required) & set(profile.citizenships))
    return RuleResult(
        rule_id=rule_id,
        status=ELIGIBLE if met else INELIGIBLE,
        reason=f"Citizenship requirement {required_text} "
        + ("is met by the profile." if met else "is not met by the profile's citizenship."),
        requirement_id=requirement.id,
        details={"required": required},
    )


def check_unsupported(
    profile: ProfileInput, opportunity: OpportunityInput, requirement: RequirementInput
) -> RuleResult:
    return RuleResult(
        rule_id="ELIG-REQ-001",
        status=NEEDS_VERIFICATION,
        reason=f"Requirement type {requirement.requirement_type.value} isn't evaluated by"
        f" eligibility rules {RULES_VERSION}; verify it manually.",
        requirement_id=requirement.id,
    )


_ASSESSMENT_REASONS = {
    RequirementsAssessmentStatus.UNASSESSED: "The opportunity's hard eligibility requirements"
    " haven't been assessed yet, so eligibility can't be confirmed.",
    RequirementsAssessmentStatus.PARTIAL: "The opportunity's hard eligibility requirements are"
    " only partially assessed; requirements that aren't represented yet may apply.",
    RequirementsAssessmentStatus.COMPLETE: "All of the opportunity's hard eligibility requirements"
    " are assessed and represented.",
}


def check_requirements_assessment(opportunity: OpportunityInput) -> RuleResult:
    """System-level rule about the requirement set as a whole, not one requirement row."""
    assessment = opportunity.requirements_assessment_status
    return RuleResult(
        rule_id="ELIG-REQ-000",
        status=ELIGIBLE
        if assessment is RequirementsAssessmentStatus.COMPLETE
        else NEEDS_VERIFICATION,
        reason=_ASSESSMENT_REASONS[assessment],
        details={"requirements_assessment_status": assessment.value},
    )


RULES: dict[RequirementType, Rule] = {
    RequirementType.MINIMUM_AGE: check_minimum_age,
    RequirementType.EDUCATION: check_education,
    RequirementType.CITIZENSHIP: check_citizenship,
}


def evaluate_requirement(
    profile: ProfileInput, opportunity: OpportunityInput, requirement: RequirementInput
) -> RuleResult:
    rule = RULES.get(requirement.requirement_type, check_unsupported)
    try:
        return rule(profile, opportunity, requirement)
    except ValidationError:
        schema = REQUIREMENT_VALUE_SCHEMAS[requirement.requirement_type]
        return RuleResult(
            rule_id="ELIG-REQ-001",
            status=NEEDS_VERIFICATION,
            reason=f"The {requirement.requirement_type.value} requirement value doesn't match"
            f" {schema.__name__}; verify it manually.",
            requirement_id=requirement.id,
        )
