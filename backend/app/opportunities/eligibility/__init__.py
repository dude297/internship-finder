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
    RuleResult,
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
        depends_on_projected_status=depends_on_projection(status, results),
        rule_results=results,
    )


def depends_on_projection(status: EligibilityStatus, results: Sequence[RuleResult]) -> bool:
    """Whether the final status actually depends on a projected education status.

    Eligible needs every result to pass, so any projected pass is load-bearing. Otherwise the
    status is decided by the results that produced it: if any of those is non-projected, it
    stands on its own and the outcome doesn't depend on projection."""
    if status is EligibilityStatus.ELIGIBLE:
        return any(r.depends_on_projected_status for r in results)
    decisive = [r for r in results if r.status is status]
    return bool(decisive) and all(r.depends_on_projected_status for r in decisive)


__all__ = [
    "RULES_VERSION",
    "EligibilityEvaluation",
    "depends_on_projection",
    "evaluate_eligibility",
]
