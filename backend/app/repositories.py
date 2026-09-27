"""Persistence helpers that add something beyond plain `session.add` / `session.get`.

Callers own the transaction; these functions only flush.
"""

import hashlib
import json
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
from app.opportunities.eligibility import RULES_VERSION, EligibilityEvaluation, evaluate_eligibility
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput


def get_profile(session: Session) -> Profile | None:
    """The owner's canonical profile. Single-user: the API only ever creates one row."""
    return session.scalars(
        select(Profile).order_by(Profile.created_at, Profile.id).limit(1)
    ).first()


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


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def eligibility_fingerprint(
    profile: ProfileInput, opportunity: OpportunityInput, requirements: list[RequirementInput]
) -> str:
    """SHA-256 of everything that determines an evaluation (ADR-008 §9): the rules version, the
    canonical profile inputs, the opportunity's reference dates and assessment status, and its
    requirements without their row IDs, sorted. Canonical JSON: sorted keys, no whitespace,
    ISO dates. A change detector, not a security control."""
    rows = sorted(_dump(r.model_dump(mode="json", exclude={"id"})) for r in requirements)
    document = {
        "rules_version": RULES_VERSION,
        "profile": profile.model_dump(mode="json"),
        "opportunity": opportunity.model_dump(mode="json"),
        "requirements": rows,
    }
    return hashlib.sha256(_dump(document).encode()).hexdigest()


def save_evaluation(
    session: Session,
    profile_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    evaluation: EligibilityEvaluation,
    fingerprint: str | None = None,
) -> OpportunityEvaluation:
    """Append an evaluation (history is kept; nothing is overwritten)."""
    row = OpportunityEvaluation(
        profile_id=profile_id,
        opportunity_id=opportunity_id,
        eligibility_status=evaluation.status,
        eligibility_rules_version=evaluation.rules_version,
        depends_on_projected_status=evaluation.depends_on_projected_status,
        evaluated_at=datetime.now(UTC),
        input_fingerprint=fingerprint,
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


def _inputs(
    profile: Profile, opportunity: Opportunity
) -> tuple[ProfileInput, OpportunityInput, list[RequirementInput]]:
    return (
        ProfileInput.model_validate(profile),
        OpportunityInput.model_validate(opportunity),
        [RequirementInput.model_validate(r) for r in opportunity.requirements],
    )


def evaluate_and_save(
    session: Session, profile: Profile, opportunity: Opportunity
) -> OpportunityEvaluation:
    """Evaluate eligibility from the canonical profile and the opportunity's requirements, and
    append it (a forced evaluation: always a new row)."""
    inputs = _inputs(profile, opportunity)
    evaluation = evaluate_eligibility(*inputs)
    return save_evaluation(
        session, profile.id, opportunity.id, evaluation, eligibility_fingerprint(*inputs)
    )


def evaluate_if_changed(
    session: Session, profile: Profile, opportunity: Opportunity
) -> OpportunityEvaluation | None:
    """Automatic evaluation: append one only when the inputs differ from the latest evaluation's
    (by fingerprint). Returns None when nothing relevant changed."""
    inputs = _inputs(profile, opportunity)
    fingerprint = eligibility_fingerprint(*inputs)
    latest = latest_evaluation(session, profile.id, opportunity.id)
    if latest is not None and latest.input_fingerprint == fingerprint:
        return None
    evaluation = evaluate_eligibility(*inputs)
    return save_evaluation(session, profile.id, opportunity.id, evaluation, fingerprint)


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
