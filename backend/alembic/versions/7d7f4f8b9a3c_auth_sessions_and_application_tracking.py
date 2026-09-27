"""auth sessions and application tracking

Milestone 2 (ADR-007): the single owner account, opaque server-side sessions (only the
SHA-256 of each token is stored), and application tracking (at most one row per opportunity).

Also adds one CHECK constraint to the existing `profiles` table: when both are set,
expected_graduation_date must be strictly after education_status_as_of (the education
transition takes effect on the graduation date). An existing profile that violates it makes
the upgrade fail; fix the dates, then upgrade. Downgrade drops the constraint and the three
new tables, returning exactly to the Milestone 1 schema.

Revision ID: 7d7f4f8b9a3c
Revises: 3b9c6b57bb60
Create Date: 2026-09-27 00:40:39.848838

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d7f4f8b9a3c"
down_revision: str | Sequence[str] | None = "3b9c6b57bb60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_users",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_users")),
        sa.UniqueConstraint("username", name=op.f("uq_auth_users_username")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name=op.f("fk_auth_sessions_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "applications",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "saved",
                "applying",
                "applied",
                "interview",
                "offer",
                "accepted",
                "rejected",
                "withdrawn",
                name="application_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('saved', 'applying', 'applied', 'interview', 'offer', 'accepted', 'rejected', 'withdrawn')",
            name=op.f("ck_applications_application_status"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_applications_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("opportunity_id", name=op.f("uq_applications_opportunity_id")),
    )
    op.create_check_constraint(
        op.f("ck_profiles_graduation_after_status_as_of"),
        "profiles",
        "expected_graduation_date IS NULL OR education_status_as_of IS NULL"
        " OR expected_graduation_date > education_status_as_of",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_profiles_graduation_after_status_as_of"), "profiles", type_="check")
    op.drop_table("applications")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
