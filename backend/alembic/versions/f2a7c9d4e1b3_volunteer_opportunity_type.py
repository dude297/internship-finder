"""volunteer opportunity type

Milestone 7.1: opportunities.opportunity_type accepts 'volunteer'.

Additive only: the CHECK is widened, no row changes, no backfill (existing 'other' rows stay
'other'). Downgrade refuses to run while a volunteer opportunity exists, rather than rewriting its
type.

Revision ID: f2a7c9d4e1b3
Revises: e6d1a4b8c2f9
Create Date: 2026-10-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7c9d4e1b3"
down_revision: str | Sequence[str] | None = "e6d1a4b8c2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES_BEFORE = (
    "internship",
    "research",
    "fellowship",
    "summer_program",
    "scholarship",
    "competition",
    "other",
)
TYPES_AFTER = (*TYPES_BEFORE, "volunteer")
TYPE_CHECK = "ck_opportunities_opportunity_type"


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f(TYPE_CHECK), "opportunities", type_="check")
    op.create_check_constraint(
        op.f(TYPE_CHECK), "opportunities", _in("opportunity_type", TYPES_AFTER)
    )


def downgrade() -> None:
    """Downgrade schema."""
    volunteer = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM opportunities WHERE opportunity_type = 'volunteer'")
    )
    if volunteer:
        raise RuntimeError(
            f"{volunteer} volunteer opportunit(ies) exist; the previous schema can't hold them."
            " Refusing to downgrade rather than rewrite their type."
        )
    op.drop_constraint(op.f(TYPE_CHECK), "opportunities", type_="check")
    op.create_check_constraint(
        op.f(TYPE_CHECK), "opportunities", _in("opportunity_type", TYPES_BEFORE)
    )
