"""opportunity ingestion and deduplication

Milestone 3 (ADR-008): the source registry with the built-in discovery feed, ingestion run
history and bounded run errors, cross-source opportunity identifiers, source-record lifecycle
(active/closed, source timestamps, content hash), canonical `posted_at`, manual-curation
protection, and the evaluation input fingerprint.

Also reconciles `ck_profiles_graduation_after_status_as_of`. That constraint was added to
revision 7d7f4f8b9a3c during PR #5 review, before merge, so a development database upgraded to
the earlier local version of 7d7f4f8b9a3c reports that revision but lacks the constraint. The
upgrade adds it when it's missing and does nothing when it exists (fresh databases get it from
7d7f4f8b9a3c). Downgrade deliberately leaves it in place: it belongs to 7d7f4f8b9a3c's intended
schema, so a database downgraded to 7d7f4f8b9a3c must still have it. As in 7d7f4f8b9a3c, an
existing profile that violates it makes the upgrade fail; fix the dates, then upgrade.

Existing opportunities were all created by hand before this revision, so they are backfilled as
manually curated (`manually_curated_at = updated_at`). Downgrade drops everything else added
here, including all ingestion data and imported source-record metadata.

Revision ID: 726372d627b8
Revises: 7d7f4f8b9a3c
Create Date: 2026-09-27 05:09:13.300387

"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "726372d627b8"
down_revision: str | Sequence[str] | None = "7d7f4f8b9a3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRADUATION_CHECK = "ck_profiles_graduation_after_status_as_of"
# The built-in broad discovery feed (application-owned; its endpoint is hard-coded in the
# community-feed adapter, keyed by this identifier).
BUILTIN_FEED_ID = "6f0b1c9e-3c1a-4c7e-9b8e-2d7f1a4e5c01"
RUN_COUNTS = (
    "fetched",
    "normalized",
    "created",
    "updated",
    "deduplicated",
    "unchanged",
    "closed",
    "reactivated",
    "invalid",
    "error",
)


def _enum(name: str, *values: str) -> sa.Enum:
    # One named ck_ CHECK per enum is declared explicitly on each table.
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _reconcile_graduation_check() -> None:
    exists = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint"
                " WHERE conname = :name AND conrelid = 'profiles'::regclass"
            ),
            {"name": GRADUATION_CHECK},
        )
        .first()
    )
    if exists is None:
        op.create_check_constraint(
            op.f(GRADUATION_CHECK),
            "profiles",
            "expected_graduation_date IS NULL OR education_status_as_of IS NULL"
            " OR expected_graduation_date > education_status_as_of",
        )


def upgrade() -> None:
    """Upgrade schema."""
    _reconcile_graduation_check()

    ingestion_sources = op.create_table(
        "ingestion_sources",
        sa.Column(
            "kind",
            _enum("ingestion_source_kind", "community_feed", "greenhouse", "lever"),
            nullable=False,
        ),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("region", _enum("source_region", "global", "eu"), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "(kind = 'lever') = (region IS NOT NULL)",
            name=op.f("ck_ingestion_sources_region_iff_lever"),
        ),
        sa.CheckConstraint(
            "kind IN ('community_feed', 'greenhouse', 'lever')",
            name=op.f("ck_ingestion_sources_ingestion_source_kind"),
        ),
        sa.CheckConstraint(
            "region IN ('global', 'eu')", name=op.f("ck_ingestion_sources_source_region")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_sources")),
        sa.UniqueConstraint(
            "kind",
            "identifier",
            "region",
            name=op.f("uq_ingestion_sources_kind_identifier_region"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum("ingestion_run_status", "running", "success", "partial", "failed", "no_change"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_generated_at", sa.DateTime(timezone=True), nullable=True),
        *(
            sa.Column(f"{name}_count", sa.Integer(), server_default="0", nullable=False)
            for name in RUN_COUNTS
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed', 'no_change')",
            name=op.f("ck_ingestion_runs_ingestion_run_status"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["ingestion_sources.id"],
            name=op.f("fk_ingestion_runs_source_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        "ix_ingestion_runs_source_id_started_at", "ingestion_runs", ["source_id", "started_at"]
    )
    op.create_table(
        "ingestion_run_errors",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column(
            "stage",
            _enum("ingestion_stage", "fetch", "validate", "normalize", "identify", "persist"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('fetch', 'validate', 'normalize', 'identify', 'persist')",
            name=op.f("ck_ingestion_run_errors_ingestion_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_ingestion_run_errors_run_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_run_errors")),
    )
    op.create_index(op.f("ix_ingestion_run_errors_run_id"), "ingestion_run_errors", ["run_id"])
    op.create_table(
        "opportunity_identifiers",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_identifiers_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_identifiers")),
        sa.UniqueConstraint(
            "namespace", "value", name=op.f("uq_opportunity_identifiers_namespace_value")
        ),
    )
    op.create_index(
        op.f("ix_opportunity_identifiers_opportunity_id"),
        "opportunity_identifiers",
        ["opportunity_id"],
    )

    op.add_column("opportunities", sa.Column("posted_at", sa.DateTime(timezone=True)))
    op.add_column("opportunities", sa.Column("manually_curated_at", sa.DateTime(timezone=True)))
    op.create_index(op.f("ix_opportunities_posted_at"), "opportunities", ["posted_at"])
    op.execute("UPDATE opportunities SET manually_curated_at = updated_at")

    op.add_column("opportunity_evaluations", sa.Column("input_fingerprint", sa.String(64)))

    op.add_column("opportunity_source_records", sa.Column("ingestion_source_id", sa.Uuid()))
    op.add_column(
        "opportunity_source_records",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    for column in ("closed_at", "source_published_at", "source_updated_at"):
        op.add_column("opportunity_source_records", sa.Column(column, sa.DateTime(timezone=True)))
    op.add_column("opportunity_source_records", sa.Column("content_hash", sa.String(64)))
    op.create_index(
        "ix_opportunity_source_records_ingestion_source_id_is_active",
        "opportunity_source_records",
        ["ingestion_source_id", "is_active"],
    )
    op.create_foreign_key(
        op.f("fk_opportunity_source_records_ingestion_source_id"),
        "opportunity_source_records",
        "ingestion_sources",
        ["ingestion_source_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_opportunity_source_records_closed_iff_inactive"),
        "opportunity_source_records",
        "is_active = (closed_at IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_opportunity_source_records_content_hash_length"),
        "opportunity_source_records",
        "content_hash IS NULL OR length(content_hash) = 64",
    )

    op.bulk_insert(
        ingestion_sources,
        [
            {
                "id": BUILTIN_FEED_ID,
                "kind": "community_feed",
                "identifier": "zshah-tech-internships",
                "region": None,
                "display_name": "Tech Internship Discovery Feed",
                "enabled": True,
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema. Leaves ck_profiles_graduation_after_status_as_of (see above)."""
    for name in ("content_hash_length", "closed_iff_inactive"):
        op.drop_constraint(
            op.f(f"ck_opportunity_source_records_{name}"),
            "opportunity_source_records",
            type_="check",
        )
    op.drop_constraint(
        op.f("fk_opportunity_source_records_ingestion_source_id"),
        "opportunity_source_records",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_opportunity_source_records_ingestion_source_id_is_active",
        table_name="opportunity_source_records",
    )
    for column in (
        "content_hash",
        "source_updated_at",
        "source_published_at",
        "closed_at",
        "is_active",
        "ingestion_source_id",
    ):
        op.drop_column("opportunity_source_records", column)
    op.drop_column("opportunity_evaluations", "input_fingerprint")
    op.drop_index(op.f("ix_opportunities_posted_at"), table_name="opportunities")
    op.drop_column("opportunities", "manually_curated_at")
    op.drop_column("opportunities", "posted_at")
    op.drop_index(
        op.f("ix_opportunity_identifiers_opportunity_id"), table_name="opportunity_identifiers"
    )
    op.drop_table("opportunity_identifiers")
    op.drop_index(op.f("ix_ingestion_run_errors_run_id"), table_name="ingestion_run_errors")
    op.drop_table("ingestion_run_errors")
    op.drop_index("ix_ingestion_runs_source_id_started_at", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("ingestion_sources")
