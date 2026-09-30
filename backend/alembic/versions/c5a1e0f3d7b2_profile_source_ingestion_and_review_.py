"""profile source ingestion and fact review state

Milestone 5 (ADR-011):

- profile_source_artifacts: the original uploaded bytes (BYTEA), 1:1 with profile_sources,
  deleted with their source
- profile_sources: content_type, byte_size, parser_name, parser_version; UNIQUE
  (profile_id, content_sha256) so the same file can't be uploaded twice
- profile_facts.review_state (pending | accepted | rejected), NOT NULL, with server default
  'accepted'. The default exists for deployment compatibility with the immediately previous
  (Milestone 4) application, whose manual Match Profile inserts don't name review_state; it is
  not an invitation for Milestone 5 code to omit it, and the CHECK below makes an unverified
  non-manual insert that omits it fail regardless. Backfill matches the fit filter it replaces:
  user-verified or manual facts are `accepted`, everything else `pending`, so upgrading changes
  no fit input. CHECK: a non-manual fact is `accepted` exactly when `verified_by_user`.

Downgrade drops these (uploaded files and review states are lost). Rejected and pending
imported facts are unverified, so the previous fit filter still ignores them.

Revision ID: c5a1e0f3d7b2
Revises: b41e7c9d2f60
Create Date: 2026-09-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5a1e0f3d7b2"
down_revision: str | Sequence[str] | None = "b41e7c9d2f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVIEW_STATES = ("pending", "accepted", "rejected")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "profile_source_artifacts",
        sa.Column("profile_source_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_source_id"],
            ["profile_sources.id"],
            name=op.f("fk_profile_source_artifacts_profile_source_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profile_source_id", name=op.f("pk_profile_source_artifacts")),
    )

    op.add_column("profile_sources", sa.Column("content_type", sa.String(100), nullable=True))
    op.add_column("profile_sources", sa.Column("byte_size", sa.Integer(), nullable=True))
    op.add_column("profile_sources", sa.Column("parser_name", sa.String(100), nullable=True))
    op.add_column("profile_sources", sa.Column("parser_version", sa.String(50), nullable=True))
    op.create_check_constraint(
        op.f("ck_profile_sources_byte_size_positive"),
        "profile_sources",
        "byte_size IS NULL OR byte_size > 0",
    )
    op.create_unique_constraint(
        op.f("uq_profile_sources_profile_id_content_sha256"),
        "profile_sources",
        ["profile_id", "content_sha256"],
    )

    op.add_column(
        "profile_facts",
        sa.Column(
            "review_state",
            # The CHECK is created explicitly below (see 3b9c6b57bb60).
            sa.Enum(
                *REVIEW_STATES,
                name="fact_review_state",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            # PostgreSQL fills every existing row with this default; see the module docstring
            # for why the default stays after the migration instead of being dropped.
            server_default="accepted",
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE profile_facts SET review_state = 'pending'"
        " WHERE extraction_method <> 'manual' AND NOT verified_by_user"
    )
    op.alter_column("profile_facts", "review_state", nullable=False)
    op.create_check_constraint(
        op.f("ck_profile_facts_fact_review_state"),
        "profile_facts",
        f"review_state IN ({', '.join(repr(v) for v in REVIEW_STATES)})",
    )
    op.create_check_constraint(
        op.f("ck_profile_facts_review_state_matches_verified"),
        "profile_facts",
        "extraction_method = 'manual' OR (review_state = 'accepted') = verified_by_user",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("ck_profile_facts_review_state_matches_verified"), "profile_facts", type_="check"
    )
    op.drop_constraint(op.f("ck_profile_facts_fact_review_state"), "profile_facts", type_="check")
    op.drop_column("profile_facts", "review_state")

    op.drop_constraint(
        op.f("uq_profile_sources_profile_id_content_sha256"), "profile_sources", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_profile_sources_byte_size_positive"), "profile_sources", type_="check"
    )
    op.drop_column("profile_sources", "parser_version")
    op.drop_column("profile_sources", "parser_name")
    op.drop_column("profile_sources", "byte_size")
    op.drop_column("profile_sources", "content_type")

    op.drop_table("profile_source_artifacts")
