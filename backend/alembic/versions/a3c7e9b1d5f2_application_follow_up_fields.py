"""application follow-up fields

Milestone 10 (ADR-020): applications.next_action / next_action_due / interview_at, the owner's
private follow-up reminders for the Action Inbox. Additive and nullable; no data change.

Revision ID: a3c7e9b1d5f2
Revises: d4f8a1c6e2b9
Create Date: 2026-10-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c7e9b1d5f2"
down_revision: str | Sequence[str] | None = "d4f8a1c6e2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("next_action", sa.String(length=200)))
    op.add_column("applications", sa.Column("next_action_due", sa.Date()))
    op.add_column("applications", sa.Column("interview_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("applications", "interview_at")
    op.drop_column("applications", "next_action_due")
    op.drop_column("applications", "next_action")
