"""requirement candidates, review staleness, and Ashby sources

Milestone 6 (ADR-012):

- opportunity_requirement_candidates: deterministic requirement proposals and their owner review
  state. UNIQUE (opportunity_id, semantic_key). Eligibility never reads this table.
- opportunities.requirements_stale_since: a source update changed the posting text after review
- opportunities.requirement_extraction_fingerprint: what the last extraction ran on (64 hex)
- ingestion_sources.kind accepts 'ashby'

Additive only: no backfill, no evaluation, no network. Existing rows keep NULL in the new columns
(never extracted, not stale), so the Milestone 5 application keeps working against this schema.

Downgrade drops the candidates table and the two columns (review decisions on suggestions are
lost; canonical requirements, which accepted suggestions created, are kept). It refuses to run
while an Ashby source exists, rather than deleting it and orphaning its source records.

Revision ID: e6d1a4b8c2f9
Revises: c5a1e0f3d7b2
Create Date: 2026-10-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6d1a4b8c2f9"
down_revision: str | Sequence[str] | None = "c5a1e0f3d7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "opportunity_requirement_candidates"
REQUIREMENT_TYPES = ("minimum_age", "education", "citizenship", "work_authorization", "other")
APPLIES_AT = ("application", "program_start", "explicit_date")
REVIEW_STATES = ("pending", "accepted", "rejected")
KINDS_BEFORE = ("community_feed", "greenhouse", "lever")
KINDS_AFTER = (*KINDS_BEFORE, "ashby")
KIND_CHECK = "ck_ingestion_sources_ingestion_source_kind"
FINGERPRINT_CHECK = "ck_opportunities_requirement_extraction_fingerprint_length"


def _enum(name: str, *values: str) -> sa.Enum:
    # The CHECK is created explicitly below (see 3b9c6b57bb60).
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_key", sa.String(64), nullable=False),
        sa.Column(
            "requirement_type",
            _enum("candidate_requirement_type", *REQUIREMENT_TYPES),
            nullable=False,
        ),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("applies_at", _enum("candidate_applies_at", *APPLIES_AT), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("source_text", sa.String(500), nullable=False),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(50), nullable=False),
        sa.Column("review_state", _enum("candidate_review_state", *REVIEW_STATES), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("accepted_requirement_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            _in("requirement_type", REQUIREMENT_TYPES),
            name=op.f(f"ck_{TABLE}_candidate_requirement_type"),
        ),
        sa.CheckConstraint(
            _in("applies_at", APPLIES_AT), name=op.f(f"ck_{TABLE}_candidate_applies_at")
        ),
        sa.CheckConstraint(
            _in("review_state", REVIEW_STATES), name=op.f(f"ck_{TABLE}_candidate_review_state")
        ),
        sa.CheckConstraint(
            "length(semantic_key) = 64", name=op.f(f"ck_{TABLE}_semantic_key_length")
        ),
        sa.CheckConstraint(
            "(applies_at = 'explicit_date' AND reference_date IS NOT NULL)"
            " OR (applies_at <> 'explicit_date' AND reference_date IS NULL)",
            name=op.f(f"ck_{TABLE}_reference_date_iff_explicit"),
        ),
        sa.CheckConstraint(
            "accepted_requirement_id IS NULL OR review_state = 'accepted'",
            name=op.f(f"ck_{TABLE}_linked_only_when_accepted"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f(f"fk_{TABLE}_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_requirement_id"],
            ["opportunity_requirements.id"],
            name=op.f(f"fk_{TABLE}_accepted_requirement_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "opportunity_id", "semantic_key", name=op.f(f"uq_{TABLE}_opportunity_id_semantic_key")
        ),
    )
    op.create_index(op.f(f"ix_{TABLE}_accepted_requirement_id"), TABLE, ["accepted_requirement_id"])

    op.add_column(
        "opportunities",
        sa.Column("requirements_stale_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("requirement_extraction_fingerprint", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        op.f(FINGERPRINT_CHECK),
        "opportunities",
        "requirement_extraction_fingerprint IS NULL"
        " OR length(requirement_extraction_fingerprint) = 64",
    )

    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_AFTER))


def downgrade() -> None:
    """Downgrade schema."""
    ashby = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM ingestion_sources WHERE kind = 'ashby'")
    )
    if ashby:
        raise RuntimeError(
            f"{ashby} Ashby source(s) exist; the previous schema can't hold them. Refusing to"
            " downgrade rather than delete them and orphan their source records."
        )
    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_BEFORE))

    op.drop_constraint(op.f(FINGERPRINT_CHECK), "opportunities", type_="check")
    op.drop_column("opportunities", "requirement_extraction_fingerprint")
    op.drop_column("opportunities", "requirements_stale_since")

    op.drop_index(op.f(f"ix_{TABLE}_accepted_requirement_id"), table_name=TABLE)
    op.drop_table(TABLE)
