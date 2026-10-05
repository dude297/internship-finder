"""smartrecruiters and program registry

Milestone 8 (ADR-014):
- ingestion_sources.kind accepts 'smartrecruiters' and 'curated_registry'
- opportunity_source_records.source_type accepts 'curated_registry'
- the built-in scope rule covers the registry too
- opportunities gains the registry's date-trust columns (program_cycle, typical_open_window,
  typical_close_window, verify_by), all nullable, no backfill
- seeds the built-in program registry source (enabled)

Downgrade refuses while a SmartRecruiters source or any registry record exists, rather than
deleting data.

Revision ID: a8c3e5f7b9d1
Revises: f2a7c9d4e1b3
Create Date: 2026-10-04 00:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8c3e5f7b9d1"
down_revision: str | Sequence[str] | None = "f2a7c9d4e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = ("community_feed", "greenhouse", "lever", "ashby")
KINDS_AFTER = (*KINDS_BEFORE, "smartrecruiters", "curated_registry")
KIND_CHECK = "ck_ingestion_sources_ingestion_source_kind"
SOURCE_TYPES_BEFORE = ("public_feed", "ats", "career_page", "browser", "manual", "other")
SOURCE_TYPES_AFTER = (*SOURCE_TYPES_BEFORE, "curated_registry")
SOURCE_TYPE_CHECK = "ck_opportunity_source_records_source_type"
SCOPE_CHECK = "ck_ingestion_sources_builtin_scope_all"
REGISTRY_SOURCE_ID = uuid.UUID("4d2b7e1a-9c3f-4e8b-a6d5-0f1e2c3b4a59")
COLUMNS = ("program_cycle", "typical_open_window", "typical_close_window", "verify_by")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_AFTER))
    op.drop_constraint(op.f(SOURCE_TYPE_CHECK), "opportunity_source_records", type_="check")
    op.create_check_constraint(
        op.f(SOURCE_TYPE_CHECK),
        "opportunity_source_records",
        _in("source_type", SOURCE_TYPES_AFTER),
    )
    op.drop_constraint(op.f(SCOPE_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(
        op.f(SCOPE_CHECK),
        "ingestion_sources",
        "kind NOT IN ('community_feed', 'curated_registry') OR scope = 'all'",
    )

    op.add_column("opportunities", sa.Column("program_cycle", sa.String(length=20)))
    op.add_column("opportunities", sa.Column("typical_open_window", sa.String(length=100)))
    op.add_column("opportunities", sa.Column("typical_close_window", sa.String(length=100)))
    op.add_column("opportunities", sa.Column("verify_by", sa.Date()))

    op.execute(
        sa.text(
            "INSERT INTO ingestion_sources (id, kind, identifier, region, display_name, enabled,"
            " scope) VALUES (:id, 'curated_registry', 'program-registry', NULL,"
            " 'Curated Program Registry', true, 'all')"
        ).bindparams(id=REGISTRY_SOURCE_ID)
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    smartrecruiters = bind.scalar(
        sa.text("SELECT count(*) FROM ingestion_sources WHERE kind = 'smartrecruiters'")
    )
    registry_records = bind.scalar(
        sa.text(
            "SELECT count(*) FROM opportunity_source_records WHERE source_type = 'curated_registry'"
        )
    )
    if smartrecruiters or registry_records:
        raise RuntimeError(
            f"{smartrecruiters} SmartRecruiters source(s) and {registry_records} registry"
            " record(s) exist; the previous schema can't hold them. Refusing to downgrade rather"
            " than delete them."
        )
    # The registry source's (empty) run history goes with it (ON DELETE CASCADE).
    op.execute(sa.text("DELETE FROM ingestion_sources WHERE kind = 'curated_registry'"))

    for column in reversed(COLUMNS):
        op.drop_column("opportunities", column)
    op.drop_constraint(op.f(SCOPE_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(
        op.f(SCOPE_CHECK), "ingestion_sources", "kind <> 'community_feed' OR scope = 'all'"
    )
    op.drop_constraint(op.f(SOURCE_TYPE_CHECK), "opportunity_source_records", type_="check")
    op.create_check_constraint(
        op.f(SOURCE_TYPE_CHECK),
        "opportunity_source_records",
        _in("source_type", SOURCE_TYPES_BEFORE),
    )
    op.drop_constraint(op.f(KIND_CHECK), "ingestion_sources", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "ingestion_sources", _in("kind", KINDS_BEFORE))
