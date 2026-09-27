"""Paginated, filtered opportunity listing and provenance summaries (Milestone 3).

Everything is filtered and counted in SQL so a catalog of thousands never loads at once.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, defer, selectinload

from app.enums import ApplicationStatus, EligibilityStatus, OpportunitySourceType, RemoteMode
from app.models import Application, Opportunity, OpportunityEvaluation, OpportunitySourceRecord
from app.repositories import get_profile
from app.schemas.opportunity import (
    Availability,
    OpportunitySummary,
    Origin,
    SourceRecordResponse,
)

AvailabilityFilter = Literal["open", "closed", "all"]
EligibilityFilter = EligibilityStatus | Literal["not_evaluated"]
ApplicationFilter = ApplicationStatus | Literal["tracked", "untracked"]


@dataclass(frozen=True)
class Filters:
    q: str | None = None
    # open (default): an active automated record, or managed by hand. Tracked opportunities
    # whose postings closed stay reachable through "closed"/"all".
    availability: AvailabilityFilter = "open"
    # An ingestion source ID, or "manual".
    source: uuid.UUID | Literal["manual"] | None = None
    eligibility: EligibilityFilter | None = None
    application_status: ApplicationFilter | None = None
    remote_mode: RemoteMode | None = None


_record = OpportunitySourceRecord
_automated = select(_record.id).where(
    _record.opportunity_id == Opportunity.id, _record.ingestion_source_id.is_not(None)
)
_active = _automated.where(_record.is_active)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# The eligibility columns come from a subquery, so SQLAlchemy types them as Any.
def _filtered(db: Session, filters: Filters) -> Select[Opportunity, Any, Any]:
    profile = get_profile(db)
    # The current profile's latest evaluation per opportunity (same order as latest_evaluation).
    latest = (
        select(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.eligibility_status,
            OpportunityEvaluation.evaluated_at,
        )
        .where(OpportunityEvaluation.profile_id == (profile.id if profile else None))
        .ext(distinct_on(OpportunityEvaluation.opportunity_id))
        .order_by(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.evaluated_at.desc(),
            OpportunityEvaluation.id.desc(),
        )
        .subquery()
    )
    stmt = (
        select(Opportunity, latest.c.eligibility_status, latest.c.evaluated_at)
        .outerjoin(latest, latest.c.opportunity_id == Opportunity.id)
        .outerjoin(Application, Application.opportunity_id == Opportunity.id)
    )
    if filters.availability == "open":
        stmt = stmt.where(or_(exists(_active), ~exists(_automated)))
    elif filters.availability == "closed":
        stmt = stmt.where(and_(exists(_automated), ~exists(_active)))
    if filters.q:
        pattern = _like(filters.q.strip())
        stmt = stmt.where(
            or_(
                Opportunity.title.ilike(pattern, escape="\\"),
                Opportunity.organization.ilike(pattern, escape="\\"),
            )
        )
    if filters.source == "manual":
        stmt = stmt.where(
            exists(
                select(_record.id).where(
                    _record.opportunity_id == Opportunity.id,
                    _record.source_type == OpportunitySourceType.MANUAL,
                )
            )
        )
    elif filters.source is not None:
        stmt = stmt.where(
            exists(
                select(_record.id).where(
                    _record.opportunity_id == Opportunity.id,
                    _record.ingestion_source_id == filters.source,
                )
            )
        )
    if filters.eligibility == "not_evaluated":
        stmt = stmt.where(latest.c.eligibility_status.is_(None))
    elif filters.eligibility is not None:
        stmt = stmt.where(latest.c.eligibility_status == filters.eligibility)
    if filters.application_status == "tracked":
        stmt = stmt.where(Application.id.is_not(None))
    elif filters.application_status == "untracked":
        stmt = stmt.where(Application.id.is_(None))
    elif filters.application_status is not None:
        stmt = stmt.where(Application.status == filters.application_status)
    if filters.remote_mode is not None:
        stmt = stmt.where(Opportunity.remote_mode == filters.remote_mode)
    return stmt


def provenance(records: list[OpportunitySourceRecord]) -> tuple[Origin, Availability]:
    automated = [r for r in records if r.ingestion_source_id is not None]
    if not automated:
        return "manual", "manual"
    return "imported", "open" if any(r.is_active for r in automated) else "closed"


def record_name(record: OpportunitySourceRecord) -> str:
    source = record.ingestion_source
    return source.display_name if source else "Manual entry"


def records_response(records: list[OpportunitySourceRecord]) -> list[SourceRecordResponse]:
    return [
        SourceRecordResponse(
            source_name=record_name(r),
            source_type=r.source_type,
            automated=r.ingestion_source_id is not None,
            is_active=r.is_active,
            closed_at=r.closed_at,
            first_seen_at=r.first_seen_at,
            last_seen_at=r.last_seen_at,
            source_url=r.source_url,
            source_published_at=r.source_published_at,
            source_updated_at=r.source_updated_at,
        )
        for r in sorted(records, key=lambda r: (r.first_seen_at, r.id))
    ]


def list_page(
    db: Session, filters: Filters, limit: int, offset: int
) -> tuple[list[OpportunitySummary], int]:
    """One page, freshest first: posted date (unknown last), then first seen, then ID."""
    stmt = _filtered(db, filters)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.options(
            selectinload(Opportunity.application),
            selectinload(Opportunity.source_records)
            .options(defer(_record.raw_payload))
            .selectinload(_record.ingestion_source),
        )
        .order_by(
            Opportunity.posted_at.desc().nulls_last(),
            Opportunity.first_seen_at.desc(),
            Opportunity.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[OpportunitySummary] = []
    for opportunity, eligibility, evaluated_at in rows:
        origin, availability = provenance(opportunity.source_records)
        items.append(
            OpportunitySummary(
                id=opportunity.id,
                title=opportunity.title,
                organization=opportunity.organization,
                opportunity_type=opportunity.opportunity_type,
                location=opportunity.location,
                remote_mode=opportunity.remote_mode,
                application_deadline=opportunity.application_deadline,
                start_date=opportunity.start_date,
                posted_at=opportunity.posted_at,
                first_seen_at=opportunity.first_seen_at,
                requirements_assessment_status=opportunity.requirements_assessment_status,
                eligibility_status=eligibility,
                evaluated_at=evaluated_at,
                application_status=(
                    opportunity.application.status if opportunity.application else None
                ),
                origin=origin,
                availability=availability,
                source_names=sorted({record_name(r) for r in opportunity.source_records}),
            )
        )
    return items, total
