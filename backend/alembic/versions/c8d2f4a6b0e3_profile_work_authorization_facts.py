"""profile work-authorization facts

Milestone 15 (ADR-026): seven nullable boolean columns on profiles, the owner's explicit
work-authorization answers. NULL = not provided. Additive; no backfill (the old
`work_authorizations` country list is ambiguous and is never converted).

Revision ID: c8d2f4a6b0e3
Revises: a3c7e9b1d5f2
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d2f4a6b0e3"
# Chained on the head at branch time; the integrator re-chains when other migrations land.
down_revision: str | Sequence[str] | None = "a3c7e9b1d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    "work_authorized_us",
    "needs_sponsorship_now",
    "needs_sponsorship_future",
    "us_citizen",
    "us_permanent_resident",
    "us_person_export_control",
    "active_security_clearance",
)


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("profiles", sa.Column(name, sa.Boolean(), nullable=True))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("profiles", name)
