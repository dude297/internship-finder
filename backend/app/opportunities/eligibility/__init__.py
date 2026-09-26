"""Eligibility engine: the single public entry point is `evaluate_eligibility`."""

from collections.abc import Sequence

from app.enums import EligibilityStatus
from app.opportunities.eligibility.rules import (
    RULES_VERSION,
    check_requirements_assessment,
    evaluate_requirement,
)
from app.opportunities.eligibility.schemas import (
    EligibilityEvaluation,
    OpportunityInput,
    ProfileInput,
    RequirementInput,
)

# ineligible > needs_verification > eligible
_PRECEDENCE = {
    EligibilityStatus.ELIGIBLE: 0,
    EligibilityStatus.NEEDS_VERIFICATION: 1,
    EligibilityStatus.INELIGIBLE: 2,
}


def evaluate_eligibility(
    profile: ProfileInput,
    opportunity: OpportunityInput,
    requirements: Sequence[RequirementInput],
) -> EligibilityEvaluation:
    """Check the requirement set's completeness (ELIG-REQ-000), run one rule per requirement, and
    combine by precedence. No requirements → eligible only when the assessment is complete.
    Fit scoring is separate (ADR-001) and never happens here."""
    results = (check_requirements_assessment(opportunity),) + tuple(
        evaluate_requirement(profile, opportunity, r) for r in requirements
    )
    status = max((r.status for r in results), key=_PRECEDENCE.__getitem__)
    return EligibilityEvaluation(
        status=status,
        rules_version=RULES_VERSION,
        # Only results that produced the final status can make it depend on a projection.
        depends_on_projected_status=any(
            r.depends_on_projected_status and r.status is status for r in results
        ),
        rule_results=results,
    )


__all__ = ["RULES_VERSION", "EligibilityEvaluation", "evaluate_eligibility"]
