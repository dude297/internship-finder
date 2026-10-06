"""owner opportunity decisions (hide)

Milestone 9 (ADR-017): opportunities.dismissed_at / dismissed_reason, the owner's durable
"hidden / not interested" decision. Additive and nullable; no data change. Sync never touches
them, and hiding never deletes source records.

Revision ID: d4f8a1c6e2b9
Revises: b7e3d9f1a2c4
Create Date: 2026-10-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f8a1c6e2b9"
down_revision: str | Sequence[str] | None = "b7e3d9f1a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("dismissed_at", sa.DateTime(timezone=True)))
    op.add_column("opportunities", sa.Column("dismissed_reason", sa.String(length=30)))
    op.create_check_constraint(
        "dismissed_reason_needs_dismissed_at",
        "opportunities",
        "dismissed_reason IS NULL OR dismissed_at IS NOT NULL",
    )


def downgrade() -> None:
    # Dropping the columns drops the CHECK that references them.
    op.drop_column("opportunities", "dismissed_reason")
    op.drop_column("opportunities", "dismissed_at")
