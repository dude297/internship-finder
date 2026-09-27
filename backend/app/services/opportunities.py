"""Manual opportunities, their requirements, evaluation, and application tracking.

Every mutation that can change eligibility evaluates automatically when a profile exists: a new
evaluation is appended (history is kept) only when the eligibility inputs changed (ADR-008 §9).
Functions flush; the caller commits once, so an opportunity, its source record, its
requirements, and its evaluation are saved together or not at all.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.enums import ExtractionMethod, OpportunitySourceType
from app.models import (
    Application,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunitySourceRecord,
    Profile,
)
from app.repositories import evaluate_and_save, evaluate_if_changed, get_profile, latest_evaluation
from app.schemas.application import ApplicationBody
from app.schemas.opportunity import OpportunityBody, RequirementBody

MANUAL_SOURCE_NAME = "manual"


def _requirement(body: RequirementBody) -> OpportunityRequirement:
    return OpportunityRequirement(**body.model_dump(), extraction_method=ExtractionMethod.MANUAL)


def _fields(body: OpportunityBody) -> dict[str, Any]:
    return body.model_dump(exclude={"requirements"})


def get_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    return db.get(
        Opportunity,
        opportunity_id,
        options=[selectinload(Opportunity.requirements), selectinload(Opportunity.application)],
    )


def evaluate(db: Session, opportunity: Opportunity) -> OpportunityEvaluation | None:
    """Append an evaluation for the current profile (forced, even if nothing changed), or None
    when there's no profile yet."""
    profile = get_profile(db)
    return evaluate_and_save(db, profile, opportunity) if profile else None


def evaluate_automatically(db: Session, opportunity: Opportunity) -> None:
    """After a change: append an evaluation only if an eligibility input changed."""
    profile = get_profile(db)
    if profile is not None:
        evaluate_if_changed(db, profile, opportunity)


def evaluate_all(db: Session, profile: Profile) -> int:
    """Re-evaluate every opportunity for the profile (synchronous: fine at manual, single-user
    scale; a large catalog would need batching or a background job)."""
    opportunities = db.scalars(
        select(Opportunity).options(selectinload(Opportunity.requirements))
    ).all()
    for opportunity in opportunities:
        evaluate_and_save(db, profile, opportunity)
    return len(opportunities)


def create_opportunity(db: Session, body: OpportunityBody) -> Opportunity:
    """A manual opportunity keeps provenance like any other: one `manual` source record, with no
    external ID (nothing to fabricate)."""
    now = datetime.now(UTC)
    opportunity = Opportunity(
        **_fields(body),
        manually_curated_at=now,
        requirements=[_requirement(r) for r in body.requirements],
        source_records=[
            OpportunitySourceRecord(
                source_name=MANUAL_SOURCE_NAME,
                source_type=OpportunitySourceType.MANUAL,
                fetched_at=now,
            )
        ],
        application=None,
    )
    db.add(opportunity)
    db.flush()
    evaluate_automatically(db, opportunity)
    return opportunity


def update_opportunity(db: Session, opportunity: Opportunity, body: OpportunityBody) -> None:
    """Replace the fields and the complete requirement set, then evaluate. Old requirement rows
    are deleted; past rule results keep their text (requirement_id becomes NULL).

    An owner edit marks the opportunity curated: later syncs keep updating its source records
    but never overwrite these fields or requirements (ADR-008 §8)."""
    for name, value in _fields(body).items():
        setattr(opportunity, name, value)
    opportunity.requirements = [_requirement(r) for r in body.requirements]
    opportunity.manually_curated_at = datetime.now(UTC)
    db.flush()
    evaluate_automatically(db, opportunity)


def list_opportunities(
    db: Session,
) -> list[tuple[Opportunity, OpportunityEvaluation | None]]:
    """Opportunities (newest first) with the current profile's latest evaluation of each."""
    opportunities = db.scalars(
        select(Opportunity)
        .options(selectinload(Opportunity.application))
        .order_by(Opportunity.created_at.desc(), Opportunity.id)
    ).all()
    profile = get_profile(db)
    latest: dict[uuid.UUID, OpportunityEvaluation] = {}
    if profile is not None:
        rows = db.scalars(
            select(OpportunityEvaluation)
            .where(OpportunityEvaluation.profile_id == profile.id)
            # PostgreSQL DISTINCT ON: the first row per opportunity in this order is the latest
            # (same ordering as app.repositories.latest_evaluation).
            .ext(distinct_on(OpportunityEvaluation.opportunity_id))
            .order_by(
                OpportunityEvaluation.opportunity_id,
                OpportunityEvaluation.evaluated_at.desc(),
                OpportunityEvaluation.id.desc(),
            )
        ).all()
        latest = {row.opportunity_id: row for row in rows}
    return [(o, latest.get(o.id)) for o in opportunities]


def current_evaluation(db: Session, opportunity: Opportunity) -> OpportunityEvaluation | None:
    profile = get_profile(db)
    return latest_evaluation(db, profile.id, opportunity.id) if profile else None


def save_application(db: Session, opportunity: Opportunity, body: ApplicationBody) -> Application:
    """Start or update tracking. Any status may follow any other; eligibility is untouched."""
    if opportunity.application is None:
        opportunity.application = Application(**body.model_dump())
    else:
        for name, value in body.model_dump().items():
            setattr(opportunity.application, name, value)
    db.flush()
    return opportunity.application
