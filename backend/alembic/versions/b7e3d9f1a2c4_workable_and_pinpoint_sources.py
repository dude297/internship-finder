"""workable and pinpoint sources

Milestone 8.1 (ADR-015 §7): ingestion_sources.kind accepts 'workable' and 'pinpoint' (documented,
keyless public job-board APIs). CHECK constraint only; no data change.

Downgrade refuses while a Workable or Pinpoint source exists, rather than deleting data.

Revision ID: b7e3d9f1a2c4
Revises: a8c3e5f7b9d1
Create Date: 2026-10-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e3d9f1a2c4"
down_revision: str | Sequence[str] | None = "a8c3e5f7b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = (
    "community_feed",
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "curated_registry",
)
KINDS_AFTER = (*KINDS_BEFORE, "workable", "pinpoint")
KIND_CHECK = "ck_ingestion_sources_ingestion_source_kind"


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_AFTER))


def downgrade() -> None:
    """Downgrade schema."""
    count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM ingestion_sources WHERE kind IN ('workable', 'pinpoint')")
    )
    if count:
        raise RuntimeError(
            f"{count} Workable/Pinpoint source(s) exist; the previous schema can't hold them."
            " Refusing to downgrade rather than delete them."
        )
    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_BEFORE))
