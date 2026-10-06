"""Global requirement review queue (ADR-024): pending suggestions across opportunities.

Read side is set-based (a constant number of statements however large the catalog or page).
The only writes are the existing per-opportunity `apply_review` (ADR-012 §7); this module adds no
requirement-write path. Functions flush only; the caller commits."""

import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, contains_eager, defer, selectinload

from app.enums import FactReviewState, IngestionSourceKind, RequirementType
from app.models import (
    IngestionSource,
    Opportunity,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from app.opportunities.requirements.identity import requirement_key
from app.schemas.opportunity import RequirementResponse
from app.schemas.requirement_review import (
    BatchRejectResult,
    QueueCategoryCount,
    QueueItem,
    QueueOpportunity,
    QueuePage,
    QueueSummary,
    RequirementCandidateResponse,
    RequirementReviewRequest,
)
from app.services.discovery import is_open
from app.services.freshness import derive_freshness, source_evidence
from app.services.requirement_review import (
    InvalidReview,
    UnknownCandidate,
    apply_review,
    get_opportunity_for_review,
)

_Cand = OpportunityRequirementCandidate
_Record = OpportunitySourceRecord
_REVIEW_CHUNK = 50  # RequirementReviewRequest's per-batch limit
# Same visibility as the Action Inbox's pending-review section (ADR-020): hidden and closed
# opportunities are out of the owner's way.
_VISIBLE = (Opportunity.dismissed_at.is_(None), is_open)


def _pending_where() -> list[Any]:
    return [_Cand.review_state == FactReviewState.PENDING, *_VISIBLE]


def _filters(
    *,
    requirement_type: RequirementType | None,
    extractor_name: str | None,
    extractor_version: str | None,
    organization: str | None,
    source_kind: IngestionSourceKind | None,
    opportunity_id: uuid.UUID | None,
    posting_changed: bool,
    created_since: date | None,
) -> list[Any]:
    where: list[Any] = []
    if requirement_type is not None:
        where.append(_Cand.requirement_type == requirement_type)
    if extractor_name:
        where.append(_Cand.extractor_name == extractor_name)
    if extractor_version:
        where.append(_Cand.extractor_version == extractor_version)
    if organization:
        escaped = organization.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append(Opportunity.organization.ilike(f"%{escaped}%", escape="\\"))
    if source_kind is not None:
        where.append(
            exists().where(
                _Record.opportunity_id == Opportunity.id,
                _Record.is_active,
                IngestionSource.id == _Record.ingestion_source_id,
                IngestionSource.kind == source_kind,
            )
        )
    if opportunity_id is not None:
        where.append(_Cand.opportunity_id == opportunity_id)
    if posting_changed:
        where.append(Opportunity.requirements_stale_since.is_not(None))
    if created_since is not None:
        where.append(_Cand.created_at >= datetime.combine(created_since, time.min, tzinfo=UTC))
    return where


def build_summary(db: Session, today: date) -> QueueSummary:
    midnight = datetime.combine(today, time.min, tzinfo=UTC)
    by_type = db.execute(
        select(_Cand.requirement_type, func.count())
        .join(Opportunity, Opportunity.id == _Cand.opportunity_id)
        .where(*_pending_where())
        .group_by(_Cand.requirement_type)
        .order_by(_Cand.requirement_type)
    ).all()
    reviewed = dict(
        db.execute(
            select(_Cand.review_state, func.count())
            .where(_Cand.review_state != FactReviewState.PENDING, _Cand.updated_at >= midnight)
            .group_by(_Cand.review_state)
        ).all()
    )
    versions = db.scalars(
        select(_Cand.extractor_version)
        .where(_Cand.review_state == FactReviewState.PENDING)
        .distinct()
        .order_by(_Cand.extractor_version)
    ).all()
    return QueueSummary(
        pending_total=sum(n for _, n in by_type),
        by_type=[QueueCategoryCount(requirement_type=t, count=n) for t, n in by_type],
        accepted_today=reviewed.get(FactReviewState.ACCEPTED, 0),
        rejected_today=reviewed.get(FactReviewState.REJECTED, 0),
        today=today,
        extractor_versions=list(versions),
    )


def build_queue(
    db: Session,
    *,
    limit: int,
    offset: int,
    today: date | None = None,
    requirement_type: RequirementType | None = None,
    extractor_name: str | None = None,
    extractor_version: str | None = None,
    organization: str | None = None,
    source_kind: IngestionSourceKind | None = None,
    opportunity_id: uuid.UUID | None = None,
    posting_changed: bool = False,
    created_since: date | None = None,
) -> QueuePage:
    now = datetime.now(UTC)
    day = today or now.date()
    where = [
        *_pending_where(),
        *_filters(
            requirement_type=requirement_type,
            extractor_name=extractor_name,
            extractor_version=extractor_version,
            organization=organization,
            source_kind=source_kind,
            opportunity_id=opportunity_id,
            posting_changed=posting_changed,
            created_since=created_since,
        ),
    ]
    total = (
        db.scalar(
            select(func.count())
            .select_from(_Cand)
            .join(Opportunity, Opportunity.id == _Cand.opportunity_id)
            .where(*where)
        )
        or 0
    )
    # Grouped by opportunity (newest first) so one posting's suggestions are reviewed together.
    # ponytail: offset paging; the queue shrinks as it is worked, so the UI re-reads offset 0.
    candidates = (
        db.scalars(
            select(_Cand)
            .join(Opportunity, Opportunity.id == _Cand.opportunity_id)
            .where(*where)
            .options(
                contains_eager(_Cand.opportunity).options(
                    defer(Opportunity.description),
                    selectinload(Opportunity.requirements),
                    selectinload(Opportunity.source_records).options(
                        defer(_Record.raw_payload), selectinload(_Record.ingestion_source)
                    ),
                )
            )
            .order_by(Opportunity.first_seen_at.desc(), Opportunity.id, _Cand.created_at, _Cand.id)
            .limit(limit)
            .offset(offset)
        )
        .unique()
        .all()
    )
    evidence = source_evidence(db, now)
    items: list[QueueItem] = []
    for candidate in candidates:
        opportunity = candidate.opportunity
        key = requirement_key(candidate)
        duplicate = next(
            (r.id for r in opportunity.requirements if requirement_key(r) == key), None
        )
        fresh = derive_freshness(opportunity.source_records, evidence, opportunity.verify_by, day)
        records = sorted(opportunity.source_records, key=lambda r: (r.first_seen_at, r.id))
        items.append(
            QueueItem(
                candidate=RequirementCandidateResponse.model_validate(candidate),
                opportunity=QueueOpportunity(
                    id=opportunity.id,
                    title=opportunity.title,
                    organization=opportunity.organization,
                    application_url=opportunity.application_url,
                    first_seen_at=opportunity.first_seen_at,
                    requirements_assessment_status=opportunity.requirements_assessment_status,
                    requirements_stale_since=opportunity.requirements_stale_since,
                    freshness=fresh.state,
                    freshness_checked_at=fresh.checked_at,
                    source_names=list(dict.fromkeys(r.source_name for r in records)),
                    source_kinds=list(
                        dict.fromkeys(
                            r.ingestion_source.kind.value for r in records if r.ingestion_source
                        )
                    ),
                ),
                existing_requirements=[
                    RequirementResponse.model_validate(r) for r in opportunity.requirements
                ],
                duplicate_of=duplicate,
            )
        )
    return QueuePage(
        items=items, total=total, limit=limit, offset=offset, summary=build_summary(db, day)
    )


def reject_batch(db: Session, candidate_ids: list[uuid.UUID]) -> BatchRejectResult:
    """Reject pending suggestions across opportunities through the existing review service, one
    `apply_review` per opportunity inside the caller's single transaction. All or nothing: any
    unknown ID or non-pending candidate raises, and the caller rolls the whole batch back.
    Rejecting never accepts anything, but can still re-evaluate an opportunity (ADR-012 §7)."""
    if len(set(candidate_ids)) != len(candidate_ids):
        raise InvalidReview("A candidate ID appears more than once in the batch.")
    owner = dict(
        db.execute(select(_Cand.id, _Cand.opportunity_id).where(_Cand.id.in_(candidate_ids))).all()
    )
    by_opportunity: dict[uuid.UUID, list[uuid.UUID]] = {}
    for candidate_id in candidate_ids:
        if candidate_id not in owner:
            raise UnknownCandidate(str(candidate_id))
        by_opportunity.setdefault(owner[candidate_id], []).append(candidate_id)

    evaluated = 0
    for opportunity_id in sorted(by_opportunity):  # stable lock order: no deadlocks between batches
        ids = by_opportunity[opportunity_id]
        opportunity = get_opportunity_for_review(db, opportunity_id, lock=True)
        if opportunity is None:  # deleted since the lookup
            raise UnknownCandidate(str(ids[0]))
        state = {c.id: c.review_state for c in opportunity.requirement_candidates}
        for candidate_id in ids:  # re-checked under the lock: never un-accept by accident
            if state.get(candidate_id) is not FactReviewState.PENDING:
                raise InvalidReview(f"Candidate {candidate_id} is no longer pending.")
        for start in range(0, len(ids), _REVIEW_CHUNK):
            chunk = ids[start : start + _REVIEW_CHUNK]
            result = apply_review(db, opportunity, RequirementReviewRequest(reject=chunk))
            evaluated += int(result.evaluated)
    return BatchRejectResult(
        rejected=len(candidate_ids), opportunities=len(by_opportunity), evaluated=evaluated
    )
