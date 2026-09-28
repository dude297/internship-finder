"""reconcile the one-running-ingestion-run-per-source index

Milestone 3.5. `uq_ingestion_runs_one_running_per_source` (a partial UNIQUE index on
ingestion_runs(source_id) WHERE status = 'running') was added to revision 726372d627b8 during
PR #6 review, before merge, so a development database upgraded to the earlier local version of
726372d627b8 reports that revision but lacks the index. The upgrade creates it when it's missing
(checked in the PostgreSQL catalog) and does nothing when it exists (fresh databases get it from
726372d627b8).

If any source has more than one running run, the upgrade fails instead of choosing one or
deleting history: resolve the duplicates (e.g. mark the stale runs failed), then upgrade again.

Downgrade deliberately leaves the index in place: it belongs to 726372d627b8's intended schema,
so a database downgraded to 726372d627b8 must still have it (the same asymmetry as the
graduation-constraint reconciliation in 726372d627b8).

Revision ID: 92a17353e5a8
Revises: 726372d627b8
Create Date: 2026-09-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92a17353e5a8"
down_revision: str | Sequence[str] | None = "726372d627b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_ingestion_runs_one_running_per_source"


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid"
            " WHERE c.relname = :name AND i.indrelid = 'ingestion_runs'::regclass"
        ),
        {"name": INDEX},
    ).first()
    if exists is not None:
        return

    duplicates = bind.execute(
        sa.text(
            "SELECT source_id, count(*) FROM ingestion_runs WHERE status = 'running'"
            " GROUP BY source_id HAVING count(*) > 1"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{source_id} ({count} running)" for source_id, count in duplicates)
        raise RuntimeError(
            f"Cannot create {INDEX}: these ingestion sources have more than one run with"
            f" status 'running': {listed}. Resolve the duplicates (e.g. mark stale runs"
            " 'failed' with finished_at set), then run `alembic upgrade head` again."
        )

    op.create_index(
        INDEX,
        "ingestion_runs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    """Downgrade schema. Leaves the index in place (see above)."""
