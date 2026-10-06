"""Paginated, filtered opportunity listing and provenance summaries (Milestone 3).

Everything is filtered and counted in SQL so a catalog of thousands never loads at once.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator
from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, defer, selectinload

from app.enums import (
    ApplicationStatus,
    EligibilityStatus,
    FactReviewState,
    OpportunitySourceType,
    OpportunityType,
    RemoteMode,
    RequirementsAssessmentStatus,
)
from app.models import (
    Application,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from app.repositories import get_profile
from app.schemas.opportunity import (
    Availability,
    FitComponentSummary,
    OpportunitySummary,
    Origin,
    SourceRecordResponse,
)
from app.services.freshness import (
    DIRECT_SOURCE_TYPES,
    derive_freshness,
    healthy_source_ids,
    source_evidence,
)

AvailabilityFilter = Literal["open", "closed", "all"]
EligibilityFilter = EligibilityStatus | Literal["not_evaluated"]
ApplicationFilter = ApplicationStatus | Literal["tracked", "untracked"]
# ADR-012 §8: pending has pending candidates; stale changed since review; needs_review either.
RequirementReviewFilter = Literal["pending", "stale", "needs_review"]
# ADR-012 §14: inclusive of today, 7/14/30 days ahead only. Query params arrive as strings;
# the BeforeValidator coerces before the Literal check (pydantic doesn't coerce str->int here).
DeadlineWithin = Annotated[
    Literal[7, 14, 30], BeforeValidator(lambda v: int(v) if isinstance(v, str) else v)
]
# recommended: eligibility bucket, then fit (ADR-001, ADR-010 §1). newest: posted date.
# deadline: application_deadline ascending, nulls last (ADR-012 §14).
# discovered: first found by Internship Finder, newest first (not the provider's posted date).
Sort = Literal["recommended", "newest", "deadline", "discovered"]
# ADR-015: direct_verified, or needs_review (source_warning / program_recheck).
# ADR-017: hidden opportunities are excluded by default; "hidden" shows only them.
HiddenFilter = Literal["exclude", "include", "only"]
FreshnessFilter = Literal["direct_verified", "needs_review"]
# ADR-015: first found within the last N days (first_seen_at, never posted_at).
DiscoveredWithin = Annotated[
    Literal[1, 7], BeforeValidator(lambda v: int(v) if isinstance(v, str) else v)
]
# Opportunity + the current evaluation's status, evaluated_at, fit_score, scoring_version,
# breakdown, pending candidate count (subquery columns, so SQLAlchemy types them as Any).
Listing = Select[Opportunity, Any, Any, Any, Any, Any, Any]


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
    opportunity_type: OpportunityType | None = None
    requirements_assessment_status: RequirementsAssessmentStatus | None = None
    requirement_review: RequirementReviewFilter | None = None
    deadline_within: DeadlineWithin | None = None
    has_deadline: bool | None = None
    # ADR-014 §6: verify_by reached (true) / not reached or unset (false).
    needs_date_verification: bool | None = None
    freshness: FreshnessFilter | None = None
    discovered_within: DiscoveredWithin | None = None
    hidden: HiddenFilter = "exclude"
    # "Today" for deadline filters (ADR-012 §14): the client's local date, or the server's UTC
    # date when omitted. Never read by anything else, so tests can pass it explicitly.
    today: date | None = None


_record = OpportunitySourceRecord
_automated = select(_record.id).where(
    _record.opportunity_id == Opportunity.id, _record.ingestion_source_id.is_not(None)
)
_active = _automated.where(_record.is_active)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filtered(db: Session, filters: Filters, healthy: Collection[uuid.UUID] = ()) -> Listing:
    """`healthy`: the IDs of currently healthy sources (ADR-015), for the freshness filter."""
    profile = get_profile(db)
    # The current profile's latest evaluation per opportunity (same order as latest_evaluation).
    latest = (
        select(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.eligibility_status,
            OpportunityEvaluation.evaluated_at,
            OpportunityEvaluation.fit_score,
            OpportunityEvaluation.scoring_version,
            OpportunityEvaluation.score_breakdown,
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
    # ADR-012 §8: one aggregate subquery for pending candidate counts, outer-joined — never a
    # per-row query.
    pending = (
        select(
            OpportunityRequirementCandidate.opportunity_id.label("opportunity_id"),
            func.count().label("pending_count"),
        )
        .where(OpportunityRequirementCandidate.review_state == FactReviewState.PENDING)
        .group_by(OpportunityRequirementCandidate.opportunity_id)
        .subquery()
    )
    stmt = (
        select(
            Opportunity,
            latest.c.eligibility_status,
            latest.c.evaluated_at,
            latest.c.fit_score,
            latest.c.scoring_version,
            latest.c.score_breakdown,
            pending.c.pending_count,
        )
        .outerjoin(latest, latest.c.opportunity_id == Opportunity.id)
        .outerjoin(Application, Application.opportunity_id == Opportunity.id)
        .outerjoin(pending, pending.c.opportunity_id == Opportunity.id)
    )
    if filters.availability == "open":
        stmt = stmt.where(or_(exists(_active), ~exists(_automated)))
    elif filters.availability == "closed":
        stmt = stmt.where(and_(exists(_automated), ~exists(_active)))
    if filters.hidden == "exclude":
        stmt = stmt.where(Opportunity.dismissed_at.is_(None))
    elif filters.hidden == "only":
        stmt = stmt.where(Opportunity.dismissed_at.is_not(None))
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
    if filters.requirements_assessment_status is not None:
        stmt = stmt.where(
            Opportunity.requirements_assessment_status == filters.requirements_assessment_status
        )
    if filters.requirement_review == "pending":
        stmt = stmt.where(pending.c.pending_count.is_not(None))
    elif filters.requirement_review == "stale":
        stmt = stmt.where(Opportunity.requirements_stale_since.is_not(None))
    elif filters.requirement_review == "needs_review":
        stmt = stmt.where(
            or_(
                pending.c.pending_count.is_not(None),
                Opportunity.requirements_stale_since.is_not(None),
            )
        )
    if filters.opportunity_type is not None:
        stmt = stmt.where(Opportunity.opportunity_type == filters.opportunity_type)
    if filters.has_deadline is True:
        stmt = stmt.where(Opportunity.application_deadline.is_not(None))
    elif filters.has_deadline is False:
        stmt = stmt.where(Opportunity.application_deadline.is_(None))
    if filters.needs_date_verification is not None:
        reached = Opportunity.verify_by <= (filters.today or datetime.now(UTC).date())
        stmt = stmt.where(
            reached
            if filters.needs_date_verification
            else or_(Opportunity.verify_by.is_(None), ~reached)
        )
    if filters.freshness is not None:
        healthy_active = _active.where(_record.ingestion_source_id.in_(list(healthy)))
        if filters.freshness == "direct_verified":
            stmt = stmt.where(
                exists(healthy_active.where(_record.source_type.in_(list(DIRECT_SOURCE_TYPES))))
            )
        else:
            today = filters.today or datetime.now(UTC).date()
            stmt = stmt.where(
                or_(
                    and_(exists(_active), ~exists(healthy_active)),
                    and_(exists(_active), Opportunity.verify_by <= today),
                )
            )
    if filters.discovered_within is not None:
        since = datetime.now(UTC) - timedelta(days=filters.discovered_within)
        stmt = stmt.where(Opportunity.first_seen_at >= since)
    if filters.deadline_within is not None:
        today = filters.today or datetime.now(UTC).date()
        stmt = stmt.where(
            Opportunity.application_deadline.between(
                today, today + timedelta(days=filters.deadline_within)
            )
        )
    return stmt


def needs_date_verification(verify_by: date | None, today: date | None = None) -> bool:
    """ADR-014 §6: the registry's verify-by date has been reached."""
    return verify_by is not None and verify_by <= (today or datetime.now(UTC).date())


def program_last_verified(db: Session, opportunity_ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
    """The registry's hand-check date (`last_verified`) per program, one query for a whole page;
    only that one JSON key is read, never the payload."""
    if not opportunity_ids:
        return {}
    rows = db.execute(
        select(_record.opportunity_id, _record.raw_payload.op("->>")("last_verified")).where(
            _record.opportunity_id.in_(opportunity_ids),
            _record.source_type == OpportunitySourceType.CURATED_REGISTRY,
            _record.is_active,
        )
    ).all()
    result: dict[uuid.UUID, date] = {}
    for opportunity_id, value in rows:
        try:
            result[opportunity_id] = date.fromisoformat(value)
        except (TypeError, ValueError):
            continue
    return result


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


_ELIGIBILITY_RANK = {
    EligibilityStatus.ELIGIBLE.value: 0,
    EligibilityStatus.NEEDS_VERIFICATION.value: 1,
    EligibilityStatus.INELIGIBLE.value: 2,
}


def _order(stmt: Listing, sort: Sort, today: date) -> Listing:
    """recommended: eligible, needs verification, ineligible, then not evaluated; inside a
    bucket, fit score (highest first, none last). Fit never moves an opportunity to another
    bucket (ADR-001). deadline: upcoming deadlines soonest first, then unknown deadlines, then
    passed ones (least actionable). Every sort ends with posted date (unknown last), first seen,
    and ID, so the order is total and stable."""
    freshest = (
        Opportunity.posted_at.desc().nulls_last(),
        Opportunity.first_seen_at.desc(),
        Opportunity.id,
    )
    if sort == "newest":
        return stmt.order_by(*freshest)
    if sort == "discovered":
        return stmt.order_by(Opportunity.first_seen_at.desc(), Opportunity.id)
    if sort == "deadline":
        deadline = Opportunity.application_deadline
        group = case((deadline.is_(None), 1), (deadline < today, 2), else_=0)
        return stmt.order_by(group, deadline.asc(), *freshest)
    columns = stmt.selected_columns
    bucket = case(_ELIGIBILITY_RANK, value=columns.eligibility_status, else_=len(_ELIGIBILITY_RANK))
    return stmt.order_by(bucket, columns.fit_score.desc().nulls_last(), *freshest)


def _components(breakdown: dict[str, Any] | None) -> dict[str, FitComponentSummary] | None:
    if breakdown is None:
        return None
    return {
        key: FitComponentSummary(
            score=value["score"], weight=value["weight"], missing=value["missing"]
        )
        for key, value in breakdown["components"].items()
    }


def list_page(
    db: Session, filters: Filters, limit: int, offset: int, sort: Sort = "newest"
) -> tuple[list[OpportunitySummary], int]:
    """One page in the requested order (see _order)."""
    now = datetime.now(UTC)
    today = filters.today or now.date()
    evidence = source_evidence(db, now)
    stmt = _filtered(db, filters, healthy_source_ids(evidence))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        _order(stmt, sort, today)
        .options(
            selectinload(Opportunity.application),
            selectinload(Opportunity.source_records)
            .options(defer(_record.raw_payload))
            .selectinload(_record.ingestion_source),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    last_verified = program_last_verified(db, [row[0].id for row in rows])
    items: list[OpportunitySummary] = []
    for (
        opportunity,
        eligibility,
        evaluated_at,
        fit_score,
        scoring_version,
        breakdown,
        pending_count,
    ) in rows:
        origin, availability = provenance(opportunity.source_records)
        fresh = derive_freshness(opportunity.source_records, evidence, opportunity.verify_by, today)
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
                fit_score=fit_score,
                scoring_version=scoring_version,
                pending_requirement_count=pending_count or 0,
                requirements_stale=opportunity.requirements_stale_since is not None,
                dismissed_at=opportunity.dismissed_at,
                program_cycle=opportunity.program_cycle,
                typical_open_window=opportunity.typical_open_window,
                typical_close_window=opportunity.typical_close_window,
                verify_by=opportunity.verify_by,
                needs_date_verification=needs_date_verification(
                    opportunity.verify_by, filters.today
                ),
                fit_coverage=breakdown["coverage"] if breakdown else None,
                fit_components=_components(breakdown),
                application_status=(
                    opportunity.application.status if opportunity.application else None
                ),
                origin=origin,
                availability=availability,
                freshness=fresh.state,
                freshness_checked_at=fresh.checked_at,
                program_last_verified=last_verified.get(opportunity.id),
                source_names=sorted({record_name(r) for r in opportunity.source_records}),
            )
        )
    return items, total
