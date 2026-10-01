"""Manual opportunities, their requirements, evaluation, and application tracking.

Every mutation that can change eligibility evaluates automatically when a profile exists: a new
evaluation is appended (history is kept) only when the eligibility inputs changed (ADR-008 §9).
Functions flush; the caller commits once, so an opportunity, its source record, its
requirements, and its evaluation are saved together or not at all.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, defer, selectinload

from app.enums import ExtractionMethod, OpportunitySourceType
from app.models import (
    Application,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunitySourceRecord,
    Profile,
)
from app.repositories import (
    CatalogEvaluation,
    evaluate_and_save,
    evaluate_catalog,
    evaluate_if_changed,
    evaluation_context,
    get_profile,
    latest_evaluation,
)
from app.schemas.application import ApplicationBody
from app.schemas.opportunity import OpportunityBody, RequirementBody
from app.services.requirement_candidates import refresh_candidates

MANUAL_SOURCE_NAME = "manual"


def _requirement(body: RequirementBody) -> OpportunityRequirement:
    return OpportunityRequirement(**body.model_dump(), extraction_method=ExtractionMethod.MANUAL)


def _fields(body: OpportunityBody) -> dict[str, Any]:
    return body.model_dump(exclude={"requirements"})


def get_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    return db.get(
        Opportunity,
        opportunity_id,
        options=[
            selectinload(Opportunity.requirements),
            selectinload(Opportunity.application),
            selectinload(Opportunity.source_records)
            .options(defer(OpportunitySourceRecord.raw_payload))
            .selectinload(OpportunitySourceRecord.ingestion_source),
        ],
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


def evaluate_all(db: Session, profile: Profile) -> CatalogEvaluation:
    """Evaluate every opportunity for the profile where eligibility or fit inputs changed: one
    synchronous catalog pass in the caller's transaction (ADR-010 §9)."""
    context = evaluation_context(db, profile)
    assert context is not None
    return evaluate_catalog(db, context)


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
    refresh_candidates(db, opportunity)  # ADR-012 §6: refresh on manual create, no invalidation
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
    refresh_candidates(db, opportunity)  # ADR-012 §6: refresh on manual edit, no invalidation
    evaluate_automatically(db, opportunity)


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
