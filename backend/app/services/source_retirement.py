"""Safe source retirement (ADR-016): close a source's records through the pipeline's normal
closure path (ADR-013 §5 fallback included), then disable the source, in one transaction.

Nothing is deleted. Owner-curated opportunities keep their content (the closure never rewrites
them) and manual opportunities have no source records at all. Dry-run is the default.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import IngestionRunStatus
from app.ingestion.pipeline import ABANDONED_AFTER, close_records
from app.models import IngestionRun, IngestionSource, Opportunity, OpportunitySourceRecord
from app.repositories import evaluation_context


class RetireRefused(Exception):
    """The source is syncing right now."""


@dataclass
class RetireResult:
    applied: bool
    records_closed: int = 0  # dry-run: would close
    opportunities_closed: int = 0  # no active record left
    stayed_open: int = 0  # another active record keeps it open
    fallbacks: int = 0  # canonical content moved to the next remaining source
    curated_preserved: int = 0
    source_disabled: bool = False  # dry-run: would disable


def retire_source(
    db: Session, source: IngestionSource, *, apply: bool, now: datetime | None = None
) -> RetireResult:
    """Raises RetireRefused if the source has a running run. With apply=False nothing is
    written; with apply=True the caller commits on return and rolls back on any exception, so a
    failure leaves the source enabled and nothing closed."""
    now = now or datetime.now(UTC)
    # Serializes with a sync's start (which updates this row) and a second retirement.
    db.execute(select(IngestionSource.id).where(IngestionSource.id == source.id).with_for_update())
    db.refresh(source)  # re-read under the lock (another process may have just retired it)
    running = db.scalars(
        select(IngestionRun.started_at).where(
            IngestionRun.source_id == source.id, IngestionRun.status == IngestionRunStatus.RUNNING
        )
    ).all()
    if any(now - started < ABANDONED_AFTER for started in running):
        raise RetireRefused(f"{source.display_name} is syncing; retry when it finishes.")

    records = db.execute(
        select(OpportunitySourceRecord.id, OpportunitySourceRecord.opportunity_id).where(
            OpportunitySourceRecord.ingestion_source_id == source.id,
            OpportunitySourceRecord.is_active,
        )
    ).all()
    record_ids = {r[0] for r in records}
    opportunity_ids = {r[1] for r in records}
    stay = curated = 0
    if record_ids:
        stay = (
            db.scalar(
                select(func.count(func.distinct(OpportunitySourceRecord.opportunity_id))).where(
                    OpportunitySourceRecord.opportunity_id.in_(opportunity_ids),
                    OpportunitySourceRecord.is_active,
                    OpportunitySourceRecord.id.not_in(record_ids),
                )
            )
            or 0
        )
        curated = (
            db.scalar(
                select(func.count()).where(
                    Opportunity.id.in_(opportunity_ids),
                    Opportunity.manually_curated_at.is_not(None),
                )
            )
            or 0
        )
    result = RetireResult(
        applied=apply,
        records_closed=len(record_ids),
        opportunities_closed=len(opportunity_ids) - stay,
        stayed_open=stay,
        curated_preserved=curated,
        source_disabled=source.enabled,
    )
    if not apply:
        return result
    if record_ids:
        closure = close_records(db, record_ids, opportunity_ids, now, evaluation_context(db))
        result.records_closed = closure.closed
        result.fallbacks = closure.fallbacks
    # Rollback path is re-enable + next sync; a kept validator would answer 304 and never reopen.
    source.etag = None
    source.last_modified = None
    source.enabled = False
    db.flush()
    return result
