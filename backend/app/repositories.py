"""Persistence helpers that add something beyond plain `session.add` / `session.get`.

Callers own the transaction; these functions only flush.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    EligibilityRuleResult,
    Opportunity,
    OpportunityEvaluation,
    Profile,
)
from app.opportunities.eligibility import EligibilityEvaluation, evaluate_eligibility
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput


def get_opportunity(session: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Opportunity with its requirements and source records loaded."""
    return session.get(
        Opportunity,
        opportunity_id,
        options=[
            selectinload(Opportunity.requirements),
            selectinload(Opportunity.source_records),
        ],
    )


def save_evaluation(
    session: Session,
    profile_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    evaluation: EligibilityEvaluation,
) -> OpportunityEvaluation:
    """Append an evaluation (history is kept; nothing is overwritten)."""
    row = OpportunityEvaluation(
        profile_id=profile_id,
        opportunity_id=opportunity_id,
        eligibility_status=evaluation.status,
        eligibility_rules_version=evaluation.rules_version,
        depends_on_projected_status=evaluation.depends_on_projected_status,
        evaluated_at=datetime.now(UTC),
        rule_results=[
            EligibilityRuleResult(
                position=position,
                rule_id=result.rule_id,
                requirement_id=result.requirement_id,
                status=result.status,
                reason=result.reason,
                reference_date=result.reference_date,
                depends_on_projected_status=result.depends_on_projected_status,
                details=result.details,
            )
            for position, result in enumerate(evaluation.rule_results)
        ],
    )
    session.add(row)
    session.flush()
    return row


def evaluate_and_save(
    session: Session, profile: Profile, opportunity: Opportunity
) -> OpportunityEvaluation:
    """Evaluate eligibility from the canonical profile and the opportunity's requirements."""
    evaluation = evaluate_eligibility(
        ProfileInput.model_validate(profile),
        OpportunityInput.model_validate(opportunity),
        [RequirementInput.model_validate(r) for r in opportunity.requirements],
    )
    return save_evaluation(session, profile.id, opportunity.id, evaluation)


def latest_evaluation(
    session: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID
) -> OpportunityEvaluation | None:
    return session.scalars(
        select(OpportunityEvaluation)
        .where(
            OpportunityEvaluation.profile_id == profile_id,
            OpportunityEvaluation.opportunity_id == opportunity_id,
        )
        # id breaks evaluated_at ties: arbitrary among equal timestamps, but stable.
        .order_by(OpportunityEvaluation.evaluated_at.desc(), OpportunityEvaluation.id.desc())
        .limit(1)
    ).first()
