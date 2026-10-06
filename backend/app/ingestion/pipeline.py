"""The shared ingestion pipeline (ADR-002, ADR-008): the only code that writes imported data.

    fetch → validate → normalize (adapter) → identify → upsert → evaluate → close → run summary

Transactions: the `running` run is committed first (a per-source guard), the fetch happens
outside any transaction, every item is written in its own savepoint, and the run is finalized
and committed at the end. A failed or partial run never closes unseen records.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx2
from pydantic import ValidationError
from sqlalchemy import case, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, defer

from app.enums import (
    IngestionRunStatus,
    IngestionSourceKind,
    IngestionStage,
    OpportunitySourceType,
    RequirementsAssessmentStatus,
    SourceScope,
)
from app.ingestion.adapters import CollectRequest, SourceConfig, adapter_for
from app.ingestion.http import Fetched, FetchError, fetch_json
from app.ingestion.normalize import (
    URL,
    ItemError,
    NormalizedOpportunity,
    SnapshotError,
    canonical_url,
    is_internship_title,
)
from app.models import (
    IngestionRun,
    IngestionRunError,
    IngestionSource,
    Opportunity,
    OpportunityIdentifier,
    OpportunitySourceRecord,
)
from app.models.ingestion import RUNNING_RUN_INDEX
from app.opportunities.requirements.identity import ExtractionInput, extraction_input_fingerprint
from app.repositories import (
    EvaluationContext,
    evaluate_and_save,
    evaluate_if_changed,
    evaluation_context,
)
from app.services.requirement_candidates import invalidate_after_source_change, refresh_candidates

logger = logging.getLogger(__name__)

MAX_STORED_ERRORS = 100
# A run still `running` after this long was interrupted (e.g. the process stopped).
ABANDONED_AFTER = timedelta(minutes=15)


class SyncInProgress(Exception):
    """Another sync of the same source is running."""


class IdentityConflict(Exception):
    """The item's identifiers point at more than one canonical opportunity (ADR-008 §7)."""


@dataclass
class _Outcome:
    created: bool = False
    updated: bool = False
    deduplicated: bool = False
    reactivated: bool = False


def _add_error(
    run: IngestionRun,
    stage: IngestionStage,
    code: str,
    message: str,
    external_id: str | None = None,
) -> None:
    if len(run.errors) < MAX_STORED_ERRORS:
        run.errors.append(
            IngestionRunError(
                stage=stage, code=code[:50], message=message[:500], external_id=external_id
            )
        )


def _start_run(db: Session, source: IngestionSource, now: datetime) -> IngestionRun:
    running = db.scalars(
        select(IngestionRun).where(
            IngestionRun.source_id == source.id,
            IngestionRun.status == IngestionRunStatus.RUNNING,
        )
    ).all()
    for stale in running:
        if now - stale.started_at < ABANDONED_AFTER:
            raise SyncInProgress(f"{source.display_name} is already syncing.")
        stale.status = IngestionRunStatus.FAILED
        stale.finished_at = now
        stale.error_summary = "The run was interrupted before it finished."
    run = IngestionRun(source=source, status=IngestionRunStatus.RUNNING, started_at=now)
    source.last_attempted_at = now
    db.add(run)
    try:
        db.commit()
    except IntegrityError as error:
        # The query above is only a fast path; the partial unique index is the real guard, so a
        # concurrent start that lost the race lands here.
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == RUNNING_RUN_INDEX:
            raise SyncInProgress(f"{source.display_name} is already syncing.") from None
        raise
    return run


def _finish(db: Session, run: IngestionRun, status: IngestionRunStatus) -> IngestionRun:
    run.status = status
    run.finished_at = datetime.now(UTC)
    db.commit()
    logger.info(
        "ingestion run source=%s status=%s fetched=%d filtered=%d created=%d updated=%d"
        " deduplicated=%d"
        " unchanged=%d closed=%d reactivated=%d invalid=%d errors=%d",
        run.source.key,
        status.value,
        run.fetched_count,
        run.filtered_count,
        run.created_count,
        run.updated_count,
        run.deduplicated_count,
        run.unchanged_count,
        run.closed_count,
        run.reactivated_count,
        run.invalid_count,
        run.error_count,
    )
    return run


# ADR-015 §10: an empty snapshot can't close this many open records of one source at once.
EMPTY_SNAPSHOT_GUARD = 10


def _fail(
    db: Session, run: IngestionRun, stage: IngestionStage, code: str, message: str
) -> IngestionRun:
    run.error_count += 1
    run.error_summary = message[:500]
    _add_error(run, stage, code, message)
    return _finish(db, run, IngestionRunStatus.FAILED)


def _write_canonical(
    opportunity: Opportunity, item: NormalizedOpportunity, source_type: OpportunitySourceType
) -> None:
    """Source-derived canonical fields. Never called for curated opportunities, and never touches
    requirements or the assessment status (the owner reviews those). Dates and the date-trust
    fields are written only by the program registry (ADR-014 §6), whose deadline/start/end are
    verified dates; every other source leaves them alone."""
    opportunity.title = item.title
    opportunity.organization = item.organization
    opportunity.description = item.description
    opportunity.opportunity_type = item.opportunity_type
    opportunity.application_url = item.application_url
    opportunity.location = item.location
    opportunity.remote_mode = item.remote_mode
    opportunity.posted_at = item.posted_at
    if source_type is OpportunitySourceType.CURATED_REGISTRY:
        opportunity.application_deadline = item.application_deadline
        opportunity.start_date = item.start_date
        opportunity.end_date = item.end_date
        opportunity.program_cycle = item.program_cycle
        opportunity.typical_open_window = item.typical_open_window
        opportunity.typical_close_window = item.typical_close_window
        opportunity.verify_by = item.verify_by


def _write_record(
    record: OpportunitySourceRecord, item: NormalizedOpportunity, content_hash: str, now: datetime
) -> None:
    record.source_url = item.application_url
    record.raw_payload = item.raw_payload
    record.source_published_at = item.source_published_at
    record.source_updated_at = item.source_updated_at
    record.content_hash = content_hash
    record.is_active = True
    record.closed_at = None
    record.fetched_at = now
    record.last_seen_at = now


def _claimed(db: Session, item: NormalizedOpportunity) -> dict[tuple[str, str], uuid.UUID]:
    """Which of the item's identifiers already belong to an opportunity."""
    if not item.identifiers:
        return {}
    keys = [(i.namespace, i.value) for i in item.identifiers]
    rows = db.execute(
        select(
            OpportunityIdentifier.namespace,
            OpportunityIdentifier.value,
            OpportunityIdentifier.opportunity_id,
        ).where(tuple_(OpportunityIdentifier.namespace, OpportunityIdentifier.value).in_(keys))
    ).all()
    return {(namespace, value): opportunity_id for namespace, value, opportunity_id in rows}


def _register_identifiers(
    db: Session,
    opportunity: Opportunity,
    item: NormalizedOpportunity,
    claimed: dict[tuple[str, str], uuid.UUID],
) -> None:
    """Add the item's identifiers that nobody has claimed yet. One claimed by another
    opportunity stays with it: identifiers never move."""
    for identifier in item.identifiers:
        if (identifier.namespace, identifier.value) not in claimed:
            db.add(
                OpportunityIdentifier(
                    opportunity_id=opportunity.id,
                    namespace=identifier.namespace,
                    value=identifier.value,
                )
            )


def _has_record_from(db: Session, opportunity_id: uuid.UUID, source: IngestionSource) -> bool:
    return (
        db.scalar(
            select(OpportunitySourceRecord.id)
            .where(
                OpportunitySourceRecord.opportunity_id == opportunity_id,
                OpportunitySourceRecord.ingestion_source_id == source.id,
            )
            .limit(1)
        )
        is not None
    )


# Authority rank for canonical-field ownership (ADR-013 §1): the original posting outranks
# discovery metadata about it, which outranks anything else.
_SOURCE_RANK = case(
    (OpportunitySourceRecord.source_type == OpportunitySourceType.ATS, 0),
    (OpportunitySourceRecord.source_type == OpportunitySourceType.PUBLIC_FEED, 1),
    else_=2,
)


def _owns_canonical_fields(db: Session, record: OpportunitySourceRecord) -> bool:
    """Whether this record's updates rewrite the opportunity's canonical fields (ADR-013 §1).

    Exactly one record owns them: the highest-authority active automated record (this one
    counts as active: it was just seen), ties broken by earliest `first_seen_at` then ID. An ATS
    record always outranks a discovery-feed record, so a board added after the feed can take
    over the posting it describes (§4.3); without that rank, two sources describing one posting
    differently (the feed has no description, a board does) would overwrite each other on every
    change of either, flip-flopping the text and making a reviewed posting look changed. When
    the owning record closes, the next highest-ranked active record takes over (§5)."""
    # Lock the opportunity row first: a concurrent sync of another source holding it (e.g. an
    # uncommitted ATS takeover) is waited out, so the owner query sees its committed records.
    db.execute(
        select(Opportunity.id).where(Opportunity.id == record.opportunity_id).with_for_update()
    )
    owner = db.scalar(
        select(OpportunitySourceRecord.id)
        .where(
            OpportunitySourceRecord.opportunity_id == record.opportunity_id,
            OpportunitySourceRecord.ingestion_source_id.is_not(None),
            or_(OpportunitySourceRecord.is_active, OpportunitySourceRecord.id == record.id),
        )
        .order_by(_SOURCE_RANK, OpportunitySourceRecord.first_seen_at, OpportunitySourceRecord.id)
        .limit(1)
    )
    return owner == record.id


def _owners(
    db: Session, opportunity_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, OpportunitySourceRecord]:
    """The current canonical-field owner (ADR-013 §1) of each given opportunity, among active
    automated records of non-curated opportunities. One set-based query, not one per
    opportunity; used by the ADR-013 §5 fallback, before and after the closing update."""
    if not opportunity_ids:
        return {}
    rows = db.scalars(
        select(OpportunitySourceRecord)
        .join(Opportunity, Opportunity.id == OpportunitySourceRecord.opportunity_id)
        .where(
            OpportunitySourceRecord.opportunity_id.in_(opportunity_ids),
            OpportunitySourceRecord.ingestion_source_id.is_not(None),
            OpportunitySourceRecord.is_active,
            Opportunity.manually_curated_at.is_(None),
        )
        .ext(distinct_on(OpportunitySourceRecord.opportunity_id))
        .order_by(
            OpportunitySourceRecord.opportunity_id,
            _SOURCE_RANK,
            OpportunitySourceRecord.first_seen_at,
            OpportunitySourceRecord.id,
        )
    ).all()
    return {r.opportunity_id: r for r in rows}


def _rewrite_canonical(
    db: Session,
    source_type: OpportunitySourceType,
    opportunity: Opportunity,
    item: NormalizedOpportunity,
    now: datetime,
    context: EvaluationContext | None,
) -> None:
    """The owner's canonical-field rewrite (ADR-013 §4): compares the extraction-input
    fingerprint before and after, invalidating stale requirements and refreshing candidates only
    when it changed (ADR-012 §6), then runs `evaluate_if_changed`. A public-feed owner never
    writes `description` (ADR-013 §4): the feed has none, so a feed owner keeps the
    opportunity's last known text instead of erasing it."""
    before = extraction_input_fingerprint(ExtractionInput.model_validate(opportunity))
    kept_description = opportunity.description
    _write_canonical(opportunity, item, source_type)
    if source_type is OpportunitySourceType.PUBLIC_FEED:
        opportunity.description = kept_description
    db.flush()
    after = extraction_input_fingerprint(ExtractionInput.model_validate(opportunity))
    if before != after:
        invalidate_after_source_change(db, opportunity, now)
        refresh_candidates(db, opportunity)
    if context is not None:
        evaluate_if_changed(db, context.profile, opportunity, context)


def _normalize_stored(owner: OpportunitySourceRecord) -> NormalizedOpportunity | None:
    """Re-derive a record's item from its stored raw payload through its own adapter's per-item
    normalizer (no fetch). None if it can't be (no payload, or it no longer normalizes: logged
    with IDs and exception type only, never the payload)."""
    source = owner.ingestion_source
    if source is None or owner.raw_payload is None:
        return None
    config = SourceConfig(source.kind, source.identifier, source.region, source.display_name)
    try:
        return adapter_for(source.kind).normalize(owner.raw_payload, config)
    except (ItemError, ValidationError) as error:
        logger.warning(
            "fallback re-normalize failed opportunity_id=%s record_id=%s exception_type=%s",
            owner.opportunity_id,
            owner.id,
            type(error).__name__,
        )
        return None


def revert_to_source(db: Session, opportunity: Opportunity) -> bool:
    """ADR-017: discard the owner's edits and restore canonical content from the authoritative
    active automated record (ADR-013 §1 ranking, same as sync), through its stored raw item.
    Returns False, changing nothing, if there is no such record or it no longer normalizes.
    Clears curation, requirements, candidates and the review state (the owner re-reviews, as for
    a new import); the caller re-evaluates and commits."""
    # Lock the opportunity row first, like _owns_canonical_fields: a concurrent sync is waited out.
    db.execute(select(Opportunity.id).where(Opportunity.id == opportunity.id).with_for_update())
    owner = db.scalars(
        select(OpportunitySourceRecord)
        .where(
            OpportunitySourceRecord.opportunity_id == opportunity.id,
            OpportunitySourceRecord.ingestion_source_id.is_not(None),
            OpportunitySourceRecord.is_active,
        )
        .order_by(_SOURCE_RANK, OpportunitySourceRecord.first_seen_at, OpportunitySourceRecord.id)
        .limit(1)
    ).first()
    item = _normalize_stored(owner) if owner is not None else None
    if owner is None or item is None:
        return False
    # Only the registry writes dates and date-trust fields; every other source leaves them
    # unset, so a revert clears whatever the owner entered. A registry owner restores them from
    # its item below (registry items never merge with other sources, ADR-014 §5).
    if owner.source_type is not OpportunitySourceType.CURATED_REGISTRY:
        opportunity.application_deadline = opportunity.start_date = opportunity.end_date = None
        opportunity.program_cycle = opportunity.verify_by = None
        opportunity.typical_open_window = opportunity.typical_close_window = None
    kept_description = opportunity.description
    _write_canonical(opportunity, item, owner.source_type)
    if owner.source_type is OpportunitySourceType.PUBLIC_FEED:
        opportunity.description = kept_description  # the feed has none (ADR-013 §4)
    opportunity.requirements = []
    opportunity.requirement_candidates = []
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.UNASSESSED
    opportunity.requirements_stale_since = None
    opportunity.requirement_extraction_fingerprint = None
    opportunity.manually_curated_at = None
    db.flush()
    refresh_candidates(db, opportunity)
    return True


def _apply_fallback(
    db: Session, owner: OpportunitySourceRecord, now: datetime, context: EvaluationContext | None
) -> None:
    """ADR-013 §5: when the previous owner just closed, re-derive the new owner's canonical
    fields from its stored raw item through its own adapter's per-item normalizer (no fetch) and
    apply the same rewrite as any other takeover. A stored item that no longer normalizes (e.g.
    the adapter's schema tightened since it was stored) is logged -- IDs and exception type
    only, never the payload -- and skipped: the opportunity keeps its current text."""
    item = _normalize_stored(owner)
    if item is None:
        return
    with db.begin_nested():
        _rewrite_canonical(db, owner.source_type, owner.opportunity, item, now, context)


def _apply(
    db: Session,
    source: IngestionSource,
    record: OpportunitySourceRecord | None,
    item: NormalizedOpportunity,
    content_hash: str,
    now: datetime,
    context: EvaluationContext | None,
) -> _Outcome:
    outcome = _Outcome()
    claimed = _claimed(db, item)

    if record is not None:  # 1. same source, same external ID
        # Still subject to the conflict rule: an identifier of another opportunity rejects the
        # item before anything is written. The record's own unchanged URL is exempt, so a rule-4
        # false duplicate (sharing that URL with another record) can keep updating.
        previous_url = canonical_url(record.source_url)
        if any(
            opportunity_id != record.opportunity_id
            and not (namespace == URL and value == previous_url)
            for (namespace, value), opportunity_id in claimed.items()
        ):
            raise IdentityConflict(
                "Identifiers match more than one existing opportunity; nothing was changed."
            )
        outcome.reactivated = not record.is_active
        outcome.updated = record.content_hash != content_hash
        _write_record(record, item, content_hash, now)
        opportunity = record.opportunity
        opportunity.last_seen_at = now
        _register_identifiers(db, opportunity, item, claimed)
        if (
            (outcome.updated or outcome.reactivated)
            and opportunity.manually_curated_at is None
            and _owns_canonical_fields(db, record)
        ):
            # ADR-013 §4.1-2: its own item changed, or it reactivates.
            _rewrite_canonical(db, record.source_type, opportunity, item, now, context)
        db.flush()
        return outcome

    matches = set(claimed.values())
    if len(matches) > 1:  # 3. identity conflict: never merge
        raise IdentityConflict(
            "Identifiers match more than one existing opportunity; nothing was merged."
        )
    opportunity = db.get(Opportunity, next(iter(matches))) if matches else None
    if opportunity is not None and _has_record_from(db, opportunity.id, source):
        # 4. One source can't hold the same posting twice: a false duplicate beats a false merge.
        # (The claimed identifiers stay with the existing opportunity.)
        opportunity = None
    if opportunity is None:  # new canonical opportunity
        opportunity = Opportunity(
            title=item.title,
            organization=item.organization,
            opportunity_type=item.opportunity_type,
            first_seen_at=now,
            last_seen_at=now,
        )
        _write_canonical(opportunity, item, adapter_for(source.kind).source_type)
        db.add(opportunity)
        outcome.created = True
    else:  # 2. deduplicated onto an existing opportunity
        opportunity.last_seen_at = max(opportunity.last_seen_at, now)
        outcome.deduplicated = True
    db.flush()

    new_record = OpportunitySourceRecord(
        opportunity_id=opportunity.id,
        ingestion_source_id=source.id,
        source_name=source.key,
        source_type=adapter_for(source.kind).source_type,
        external_id=item.external_id,
        first_seen_at=now,
    )
    _write_record(new_record, item, content_hash, now)
    db.add(new_record)
    _register_identifiers(db, opportunity, item, claimed)
    db.flush()
    if outcome.created:
        refresh_candidates(db, opportunity)
        if context is not None:
            # A new opportunity has no evaluation yet.
            evaluate_and_save(db, context.profile, opportunity, context)
    elif opportunity.manually_curated_at is None and _owns_canonical_fields(db, new_record):
        # ADR-013 §4.3 takeover: a board attaching to a feed-only opportunity it outranks.
        _rewrite_canonical(db, new_record.source_type, opportunity, item, now, context)
    return outcome


def _process(
    db: Session,
    source: IngestionSource,
    run: IngestionRun,
    items: list[NormalizedOpportunity | ItemError],
    now: datetime,
) -> None:
    existing = {
        r.external_id: r
        for r in db.scalars(
            select(OpportunitySourceRecord)
            .where(OpportunitySourceRecord.ingestion_source_id == source.id)
            .options(defer(OpportunitySourceRecord.raw_payload))
        )
    }
    context = evaluation_context(db)  # the profile's inputs, read once per run
    seen: set[str] = set()
    unchanged: list[uuid.UUID] = []

    for item in items:
        if isinstance(item, ItemError):
            run.invalid_count += 1
            _add_error(run, IngestionStage.NORMALIZE, item.code, item.message, item.external_id)
            continue
        run.normalized_count += 1
        if item.external_id in seen:
            run.error_count += 1
            _add_error(
                run,
                IngestionStage.IDENTIFY,
                "duplicate_item",
                "The same ID appears more than once in the snapshot.",
                item.external_id,
            )
            continue
        seen.add(item.external_id)

        record = existing.get(item.external_id)
        content_hash = item.content_hash()
        if record is not None and record.is_active and record.content_hash == content_hash:
            unchanged.append(record.id)
            run.unchanged_count += 1
            continue
        try:
            # begin_nested() flushes the run's counters/errors first, so rolling back this
            # savepoint undoes only this item.
            with db.begin_nested():
                outcome = _apply(db, source, record, item, content_hash, now, context)
        except IdentityConflict as error:
            run.error_count += 1
            _add_error(
                run, IngestionStage.IDENTIFY, "identity_conflict", str(error), item.external_id
            )
            continue
        except SQLAlchemyError as error:
            logger.warning(
                "ingestion item failed source=%s item=%s error=%s",
                source.key,
                item.external_id,
                type(error).__name__,
            )
            run.error_count += 1
            _add_error(
                run,
                IngestionStage.PERSIST,
                "persist_failed",
                "The item couldn't be saved.",
                item.external_id,
            )
            continue
        run.created_count += outcome.created
        run.updated_count += outcome.updated
        run.deduplicated_count += outcome.deduplicated
        run.reactivated_count += outcome.reactivated
        if not (outcome.created or outcome.updated or outcome.deduplicated):
            run.unchanged_count += 1  # only reactivated

    if unchanged:  # seen again, nothing else changed: one statement instead of one per item
        db.execute(
            update(OpportunitySourceRecord)
            .where(OpportunitySourceRecord.id.in_(unchanged))
            .values(last_seen_at=now, fetched_at=now)
        )
        db.execute(
            update(Opportunity)
            .where(
                Opportunity.id.in_(
                    select(OpportunitySourceRecord.opportunity_id).where(
                        OpportunitySourceRecord.id.in_(unchanged)
                    )
                )
            )
            .values(last_seen_at=now)
        )

    if run.invalid_count == 0 and run.error_count == 0:
        # Complete successful snapshot: anything of this source not in it is closed (not deleted).
        to_close = db.execute(
            select(OpportunitySourceRecord.id, OpportunitySourceRecord.opportunity_id).where(
                OpportunitySourceRecord.ingestion_source_id == source.id,
                OpportunitySourceRecord.is_active,
                OpportunitySourceRecord.external_id.not_in(list(seen)),
            )
        ).all()
        to_close_ids = {row[0] for row in to_close}
        # ADR-013 §5 fallback: which affected, non-curated opportunities currently have one of
        # these about-to-close records as their canonical owner (looked up before closing, while
        # `is_active` still reflects it).
        owners_before = _owners(db, list({row[1] for row in to_close}))
        falling = [
            opportunity_id
            for opportunity_id, owner in owners_before.items()
            if owner.id in to_close_ids
        ]

        closed = db.scalars(
            update(OpportunitySourceRecord)
            .where(OpportunitySourceRecord.id.in_(to_close_ids))
            .values(is_active=False, closed_at=now)
            .returning(OpportunitySourceRecord.id)
        ).all()
        run.closed_count = len(closed)

        if falling:
            # The new owner, if any, is re-derived from its own stored raw item and written in
            # the same run (ADR-013 §5): correctness never depends on sync order or on the feed
            # changing, which it often doesn't (304).
            new_owners = _owners(db, falling)
            for opportunity_id in falling:
                new_owner = new_owners.get(opportunity_id)
                if new_owner is not None:
                    _apply_fallback(db, new_owner, now, context)


def sync_source(
    db: Session, source: IngestionSource, *, transport: httpx2.BaseTransport | None = None
) -> IngestionRun:
    """Sync one source and return its finished run. Raises SyncInProgress only; every source,
    network, or item failure is recorded on the run instead, and a run never stays `running`."""
    now = datetime.now(UTC)
    run = _start_run(db, source, now)
    try:
        return _sync(db, source, run, now, transport)
    except Exception:
        logger.exception("ingestion run failed unexpectedly source=%s", source.key)
        db.rollback()
        run = db.get_one(IngestionRun, run.id)
        return _fail(
            db, run, IngestionStage.PERSIST, "internal_error", "The sync failed unexpectedly."
        )


def _sync(
    db: Session,
    source: IngestionSource,
    run: IngestionRun,
    now: datetime,
    transport: httpx2.BaseTransport | None,
) -> IngestionRun:
    config = SourceConfig(source.kind, source.identifier, source.region, source.display_name)
    adapter = adapter_for(source.kind)
    try:
        if adapter.collect is not None:
            # ADR-014 §2: several requests (or none); no conditional-request validators.
            rows = db.execute(
                select(
                    OpportunitySourceRecord.external_id, OpportunitySourceRecord.raw_payload
                ).where(OpportunitySourceRecord.ingestion_source_id == source.id)
            ).all()
            known = {external_id: raw for external_id, raw in rows if external_id is not None}
            request = CollectRequest(config, source.scope, known, transport)
            fetched = Fetched(adapter.collect(request), None, None)
        else:
            fetched = fetch_json(
                adapter.url(config),
                etag=source.etag,
                last_modified=source.last_modified,
                transport=transport,
            )
    except (FetchError, SnapshotError) as error:
        return _fail(db, run, IngestionStage.FETCH, error.code, error.message)
    if fetched.not_modified:
        source.last_success_at = now
        return _finish(db, run, IngestionRunStatus.NO_CHANGE)
    try:
        snapshot = adapter.parse(fetched.data, config)
    except SnapshotError as error:
        return _fail(db, run, IngestionStage.VALIDATE, error.code, error.message)

    if (
        not snapshot.items
        and (
            db.scalar(
                select(func.count()).where(
                    OpportunitySourceRecord.ingestion_source_id == source.id,
                    OpportunitySourceRecord.is_active,
                )
            )
            or 0
        )
        >= EMPTY_SNAPSHOT_GUARD
    ):
        # ADR-015 §10: an empty answer from a source that still lists many postings is far
        # likelier a provider fault, a renamed identifier, or a placeholder than every posting
        # vanishing at once. A false open beats a mass false close: fail (Source Health turns
        # failing, so the owner sees it) and close nothing. Small boards can still empty out.
        # ponytail: all-or-nothing count guard; add a "shrank by > X%" guard if partial wipes
        # ever appear.
        return _fail(
            db,
            run,
            IngestionStage.VALIDATE,
            "empty_snapshot",
            "The source returned no postings while many are still open; nothing was closed.",
        )
    run.fetched_count = len(snapshot.items)
    run.source_generated_at = snapshot.generated_at
    items = snapshot.items
    if source.scope is SourceScope.INTERNSHIPS_ONLY:
        # Excluded items are never processed, so a complete snapshot closes records they
        # previously created (ADR-010 §10). Invalid items have no trustworthy title: kept.
        items = [i for i in items if isinstance(i, ItemError) or is_internship_title(i.title)]
        run.filtered_count = run.fetched_count - len(items)
    _process(db, source, run, items, now)

    if run.invalid_count or run.error_count:
        return _finish(db, run, IngestionRunStatus.PARTIAL)
    # Validators are kept only after a complete snapshot, so a partial run refetches in full.
    source.etag = fetched.etag
    source.last_modified = fetched.last_modified
    source.last_success_at = now
    return _finish(db, run, IngestionRunStatus.SUCCESS)


def sync_enabled_sources(
    db: Session,
    *,
    transport: httpx2.BaseTransport | None = None,
    on_skip: Callable[[IngestionSource], None] | None = None,
) -> list[IngestionRun]:
    """Sync every enabled source in turn. One source failing doesn't stop the others; a source
    that is already syncing is skipped (reported through `on_skip`, when given).

    Direct ATS sources sync before the discovery feed (ADR-013 §7), so a feed sync in the same
    run sees the boards' current state; within each tier, oldest source first, then ID.
    Correctness never depends on this order (§5 fallback), but it means fewer takeovers wait for
    the next run."""
    runs: list[IngestionRun] = []
    tier = case((IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED, 1), else_=0)
    sources = db.scalars(
        select(IngestionSource)
        .where(IngestionSource.enabled)
        .order_by(tier, IngestionSource.created_at, IngestionSource.id)
    ).all()
    for source in sources:
        try:
            runs.append(sync_source(db, source, transport=transport))
        except SyncInProgress:
            if on_skip is not None:
                on_skip(source)
            continue
    return runs
