"""initial core domain schema

Profiles with source provenance and facts, opportunities with source records and structured
requirements, and eligibility evaluations with per-rule results (ADR-006).

Enum columns are VARCHAR + one named CHECK constraint each (no native Postgres enum types),
so downgrade only needs to drop tables.

Revision ID: 3b9c6b57bb60
Revises:
Create Date: 2026-09-25 19:07:21.933870

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9c6b57bb60"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "opportunities",
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("organization", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "opportunity_type",
            sa.Enum(
                "internship",
                "research",
                "fellowship",
                "summer_program",
                "scholarship",
                "competition",
                "other",
                name="opportunity_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column(
            "remote_mode",
            sa.Enum(
                "onsite",
                "remote",
                "hybrid",
                name="remote_mode",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("application_deadline", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            "opportunity_type IN ('internship', 'research', 'fellowship', 'summer_program', 'scholarship', 'competition', 'other')",
            name=op.f("ck_opportunities_opportunity_type"),
        ),
        sa.CheckConstraint(
            "remote_mode IN ('onsite', 'remote', 'hybrid')",
            name=op.f("ck_opportunities_remote_mode"),
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name=op.f("ck_opportunities_end_not_before_start"),
        ),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name=op.f("ck_opportunities_last_seen_not_before_first"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
    )
    op.create_table(
        "profiles",
        sa.Column(
            "current_education_level",
            sa.Enum(
                "high_school",
                "undergraduate",
                "graduate",
                name="current_education_level",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("current_grade", sa.String(length=32), nullable=True),
        sa.Column("education_status_as_of", sa.Date(), nullable=True),
        sa.Column("expected_graduation_date", sa.Date(), nullable=True),
        sa.Column("expected_enrollment_date", sa.Date(), nullable=True),
        sa.Column(
            "expected_future_education_level",
            sa.Enum(
                "high_school",
                "undergraduate",
                "graduate",
                name="expected_future_education_level",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("citizenships", sa.JSON(), nullable=True),
        sa.Column("work_authorizations", sa.JSON(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
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
            "current_education_level IN ('high_school', 'undergraduate', 'graduate')",
            name=op.f("ck_profiles_current_education_level"),
        ),
        sa.CheckConstraint(
            "expected_future_education_level IN ('high_school', 'undergraduate', 'graduate')",
            name=op.f("ck_profiles_expected_future_education_level"),
        ),
        sa.CheckConstraint(
            "(current_education_level IS NULL) = (education_status_as_of IS NULL)",
            name=op.f("ck_profiles_education_level_has_as_of"),
        ),
        sa.CheckConstraint(
            "expected_enrollment_date IS NULL OR expected_graduation_date IS NULL OR expected_enrollment_date >= expected_graduation_date",
            name=op.f("ck_profiles_enrollment_not_before_graduation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
    )
    op.create_table(
        "opportunity_evaluations",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "eligibility_status",
            sa.Enum(
                "eligible",
                "needs_verification",
                "ineligible",
                name="eligibility_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("eligibility_rules_version", sa.String(length=20), nullable=False),
        sa.Column("depends_on_projected_status", sa.Boolean(), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'needs_verification', 'ineligible')",
            name=op.f("ck_opportunity_evaluations_eligibility_status"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_evaluations_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_opportunity_evaluations_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_evaluations")),
    )
    op.create_index(
        op.f("ix_opportunity_evaluations_opportunity_id"),
        "opportunity_evaluations",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_evaluations_pair_evaluated_at",
        "opportunity_evaluations",
        ["profile_id", "opportunity_id", "evaluated_at"],
        unique=False,
    )
    op.create_table(
        "opportunity_requirements",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "requirement_type",
            sa.Enum(
                "minimum_age",
                "education",
                "citizenship",
                "work_authorization",
                "other",
                name="requirement_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "applies_at",
            sa.Enum(
                "application",
                "program_start",
                "explicit_date",
                name="applies_at",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="program_start",
            nullable=False,
        ),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column(
            "extraction_method",
            sa.Enum(
                "manual",
                "deterministic_parser",
                "ai_inference",
                name="requirement_extraction_method",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("extractor_name", sa.String(length=100), nullable=True),
        sa.Column("extractor_version", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
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
            "(applies_at = 'explicit_date' AND reference_date IS NOT NULL) OR (applies_at <> 'explicit_date' AND reference_date IS NULL)",
            name=op.f("ck_opportunity_requirements_reference_date_iff_explicit"),
        ),
        sa.CheckConstraint(
            "applies_at IN ('application', 'program_start', 'explicit_date')",
            name=op.f("ck_opportunity_requirements_applies_at"),
        ),
        sa.CheckConstraint(
            "extraction_method <> 'ai_inference' OR extractor_name IS NOT NULL",
            name=op.f("ck_opportunity_requirements_ai_inference_has_extractor"),
        ),
        sa.CheckConstraint(
            "extraction_method IN ('manual', 'deterministic_parser', 'ai_inference')",
            name=op.f("ck_opportunity_requirements_requirement_extraction_method"),
        ),
        sa.CheckConstraint(
            "requirement_type IN ('minimum_age', 'education', 'citizenship', 'work_authorization', 'other')",
            name=op.f("ck_opportunity_requirements_requirement_type"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_opportunity_requirements_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_requirements_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_requirements")),
    )
    op.create_index(
        op.f("ix_opportunity_requirements_opportunity_id"),
        "opportunity_requirements",
        ["opportunity_id"],
        unique=False,
    )
    op.create_table(
        "opportunity_source_records",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "public_feed",
                "ats",
                "career_page",
                "browser",
                "manual",
                "other",
                name="source_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('public_feed', 'ats', 'career_page', 'browser', 'manual', 'other')",
            name=op.f("ck_opportunity_source_records_source_type"),
        ),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name=op.f("ck_opportunity_source_records_last_seen_not_before_first"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_source_records_opportunity_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_source_records")),
        sa.UniqueConstraint(
            "source_name",
            "external_id",
            name=op.f("uq_opportunity_source_records_source_name_external_id"),
        ),
    )
    op.create_index(
        op.f("ix_opportunity_source_records_opportunity_id"),
        "opportunity_source_records",
        ["opportunity_id"],
        unique=False,
    )
    op.create_table(
        "profile_sources",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "manual",
                "resume",
                "transcript",
                "course_list",
                "project",
                "github",
                "user_preference",
                "other",
                name="profile_source_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("storage_ref", sa.String(length=1024), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('manual', 'resume', 'transcript', 'course_list', 'project', 'github', 'user_preference', 'other')",
            name=op.f("ck_profile_sources_profile_source_kind"),
        ),
        sa.CheckConstraint(
            "content_sha256 IS NULL OR length(content_sha256) = 64",
            name=op.f("ck_profile_sources_content_sha256_length"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_profile_sources_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_sources")),
    )
    op.create_index(
        op.f("ix_profile_sources_profile_id"), "profile_sources", ["profile_id"], unique=False
    )
    op.create_table(
        "eligibility_rule_results",
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "eligible",
                "needs_verification",
                "ineligible",
                name="rule_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("depends_on_projected_status", sa.Boolean(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('eligible', 'needs_verification', 'ineligible')",
            name=op.f("ck_eligibility_rule_results_rule_status"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["opportunity_evaluations.id"],
            name=op.f("fk_eligibility_rule_results_evaluation_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["opportunity_requirements.id"],
            name=op.f("fk_eligibility_rule_results_requirement_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_rule_results")),
    )
    op.create_index(
        op.f("ix_eligibility_rule_results_evaluation_id"),
        "eligibility_rule_results",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_eligibility_rule_results_requirement_id"),
        "eligibility_rule_results",
        ["requirement_id"],
        unique=False,
    )
    op.create_table(
        "profile_facts",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "education",
                "course",
                "skill",
                "project",
                "award",
                "activity",
                "experience",
                "research",
                "preference",
                "other",
                name="fact_category",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("fact_key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "source_kind",
            sa.Enum(
                "manual",
                "resume",
                "transcript",
                "course_list",
                "project",
                "github",
                "user_preference",
                "other",
                name="fact_source_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "extraction_method",
            sa.Enum(
                "manual",
                "deterministic_parser",
                "ai_inference",
                name="fact_extraction_method",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("extractor_name", sa.String(length=100), nullable=True),
        sa.Column("extractor_version", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "verified_by_user", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
            "category IN ('education', 'course', 'skill', 'project', 'award', 'activity', 'experience', 'research', 'preference', 'other')",
            name=op.f("ck_profile_facts_fact_category"),
        ),
        sa.CheckConstraint(
            "extraction_method <> 'ai_inference' OR extractor_name IS NOT NULL",
            name=op.f("ck_profile_facts_ai_inference_has_extractor"),
        ),
        sa.CheckConstraint(
            "extraction_method IN ('manual', 'deterministic_parser', 'ai_inference')",
            name=op.f("ck_profile_facts_fact_extraction_method"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('manual', 'resume', 'transcript', 'course_list', 'project', 'github', 'user_preference', 'other')",
            name=op.f("ck_profile_facts_fact_source_kind"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_profile_facts_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_profile_facts_profile_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_source_id"],
            ["profile_sources.id"],
            name=op.f("fk_profile_facts_profile_source_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_facts")),
    )
    op.create_index(
        op.f("ix_profile_facts_profile_id"), "profile_facts", ["profile_id"], unique=False
    )
    op.create_index(
        op.f("ix_profile_facts_profile_source_id"),
        "profile_facts",
        ["profile_source_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_profile_facts_profile_source_id"), table_name="profile_facts")
    op.drop_index(op.f("ix_profile_facts_profile_id"), table_name="profile_facts")
    op.drop_table("profile_facts")
    op.drop_index(
        op.f("ix_eligibility_rule_results_requirement_id"), table_name="eligibility_rule_results"
    )
    op.drop_index(
        op.f("ix_eligibility_rule_results_evaluation_id"), table_name="eligibility_rule_results"
    )
    op.drop_table("eligibility_rule_results")
    op.drop_index(op.f("ix_profile_sources_profile_id"), table_name="profile_sources")
    op.drop_table("profile_sources")
    op.drop_index(
        op.f("ix_opportunity_source_records_opportunity_id"),
        table_name="opportunity_source_records",
    )
    op.drop_table("opportunity_source_records")
    op.drop_index(
        op.f("ix_opportunity_requirements_opportunity_id"), table_name="opportunity_requirements"
    )
    op.drop_table("opportunity_requirements")
    op.drop_index(
        "ix_opportunity_evaluations_pair_evaluated_at", table_name="opportunity_evaluations"
    )
    op.drop_index(
        op.f("ix_opportunity_evaluations_opportunity_id"), table_name="opportunity_evaluations"
    )
    op.drop_table("opportunity_evaluations")
    op.drop_table("profiles")
    op.drop_table("opportunities")
