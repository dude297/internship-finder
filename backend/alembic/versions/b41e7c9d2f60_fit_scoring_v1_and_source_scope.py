"""fit scoring v1, Match Profile preferences, and ATS source scope

Milestone 4 (ADR-010):

- profiles: fit preferences (interests, preferred_locations, remote_preference,
  availability_start/end) with CHECK availability_end >= availability_start
- opportunity_evaluations: nullable fit_score (0-100), score_breakdown, scoring_version,
  fit_input_fingerprint, all NULL or all set. Existing rows keep NULL fit fields.
- ingestion_sources.scope (all | internships_only); the built-in feed must be `all`. Existing
  sources are backfilled with `all`, so upgrading never closes any of their postings.
- ingestion_runs.filtered_count

Downgrade drops these columns and constraints (fit results, preferences, and scopes are lost;
eligibility history is kept).

Revision ID: b41e7c9d2f60
Revises: 92a17353e5a8
Create Date: 2026-09-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b41e7c9d2f60"
down_revision: str | Sequence[str] | None = "92a17353e5a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOTE_PREFERENCES = (
    "no_preference",
    "remote_preferred",
    "hybrid_preferred",
    "onsite_preferred",
    "remote_only",
)
SCOPES = ("all", "internships_only")


def _enum(name: str, *values: str) -> sa.Enum:
    # The CHECK is created explicitly below (see 3b9c6b57bb60).
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("profiles", sa.Column("interests", sa.JSON(), nullable=True))
    op.add_column("profiles", sa.Column("preferred_locations", sa.JSON(), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("remote_preference", _enum("remote_preference", *REMOTE_PREFERENCES)),
    )
    op.add_column("profiles", sa.Column("availability_start", sa.Date(), nullable=True))
    op.add_column("profiles", sa.Column("availability_end", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("ck_profiles_remote_preference"),
        "profiles",
        _in("remote_preference", REMOTE_PREFERENCES),
    )
    op.create_check_constraint(
        op.f("ck_profiles_availability_end_not_before_start"),
        "profiles",
        "availability_start IS NULL OR availability_end IS NULL"
        " OR availability_end >= availability_start",
    )

    op.add_column("opportunity_evaluations", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.add_column("opportunity_evaluations", sa.Column("score_breakdown", sa.JSON(), nullable=True))
    op.add_column(
        "opportunity_evaluations",
        sa.Column("scoring_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "opportunity_evaluations",
        sa.Column("fit_input_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_opportunity_evaluations_fit_score_range"),
        "opportunity_evaluations",
        "fit_score IS NULL OR fit_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        op.f("ck_opportunity_evaluations_fit_input_fingerprint_length"),
        "opportunity_evaluations",
        "fit_input_fingerprint IS NULL OR length(fit_input_fingerprint) = 64",
    )
    op.create_check_constraint(
        op.f("ck_opportunity_evaluations_fit_fields_together"),
        "opportunity_evaluations",
        "(fit_score IS NULL) = (scoring_version IS NULL)"
        " AND (fit_score IS NULL) = (score_breakdown IS NULL)"
        " AND (fit_score IS NULL) = (fit_input_fingerprint IS NULL)",
    )

    # Nullable first, backfilled with `all` (existing boards keep importing everything), then
    # NOT NULL. New rows get their default from the application (ATS: internships_only).
    op.add_column(
        "ingestion_sources", sa.Column("scope", _enum("source_scope", *SCOPES), nullable=True)
    )
    op.execute("UPDATE ingestion_sources SET scope = 'all'")
    op.alter_column("ingestion_sources", "scope", nullable=False)
    op.create_check_constraint(
        op.f("ck_ingestion_sources_source_scope"), "ingestion_sources", _in("scope", SCOPES)
    )
    op.create_check_constraint(
        op.f("ck_ingestion_sources_builtin_scope_all"),
        "ingestion_sources",
        "kind <> 'community_feed' OR scope = 'all'",
    )

    op.add_column(
        "ingestion_runs",
        sa.Column("filtered_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ingestion_runs", "filtered_count")

    op.drop_constraint(
        op.f("ck_ingestion_sources_builtin_scope_all"), "ingestion_sources", type_="check"
    )
    op.drop_constraint(
        op.f("ck_ingestion_sources_source_scope"), "ingestion_sources", type_="check"
    )
    op.drop_column("ingestion_sources", "scope")

    op.drop_constraint(
        op.f("ck_opportunity_evaluations_fit_fields_together"),
        "opportunity_evaluations",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_opportunity_evaluations_fit_input_fingerprint_length"),
        "opportunity_evaluations",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_opportunity_evaluations_fit_score_range"), "opportunity_evaluations", type_="check"
    )
    op.drop_column("opportunity_evaluations", "fit_input_fingerprint")
    op.drop_column("opportunity_evaluations", "scoring_version")
    op.drop_column("opportunity_evaluations", "score_breakdown")
    op.drop_column("opportunity_evaluations", "fit_score")

    op.drop_constraint(
        op.f("ck_profiles_availability_end_not_before_start"), "profiles", type_="check"
    )
    op.drop_constraint(op.f("ck_profiles_remote_preference"), "profiles", type_="check")
    op.drop_column("profiles", "availability_end")
    op.drop_column("profiles", "availability_start")
    op.drop_column("profiles", "remote_preference")
    op.drop_column("profiles", "preferred_locations")
    op.drop_column("profiles", "interests")
