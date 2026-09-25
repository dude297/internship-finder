import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import EducationLevel, ExtractionMethod, FactCategory, ProfileSourceKind


class Profile(IdMixin, TimestampMixin, Base):
    """Canonical profile: user-entered/confirmed values. The only input to hard eligibility."""

    __tablename__ = "profiles"
    __table_args__ = (
        # The current education level is a statement about a specific date.
        CheckConstraint(
            "(current_education_level IS NULL) = (education_status_as_of IS NULL)",
            name="education_level_has_as_of",
        ),
        CheckConstraint(
            "expected_enrollment_date IS NULL OR expected_graduation_date IS NULL"
            " OR expected_enrollment_date >= expected_graduation_date",
            name="enrollment_not_before_graduation",
        ),
    )

    # Time-aware education status (ADR-005). See app.profile.education for the projection.
    current_education_level: Mapped[EducationLevel | None] = mapped_column(
        str_enum(EducationLevel, "current_education_level")
    )
    current_grade: Mapped[str | None] = mapped_column(String(32))
    education_status_as_of: Mapped[date | None]
    expected_graduation_date: Mapped[date | None]
    expected_enrollment_date: Mapped[date | None]
    expected_future_education_level: Mapped[EducationLevel | None] = mapped_column(
        str_enum(EducationLevel, "expected_future_education_level")
    )

    date_of_birth: Mapped[date | None]
    # ISO 3166-1 alpha-2 codes. NULL means "not provided", never "none".
    citizenships: Mapped[list[str] | None] = mapped_column(JSON)
    work_authorizations: Mapped[list[str] | None] = mapped_column(JSON)
    location: Mapped[str | None] = mapped_column(String(200))

    sources: Mapped[list["ProfileSource"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )
    facts: Mapped[list["ProfileFact"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )


class ProfileSource(IdMixin, Base):
    """Metadata about a private source artifact. The artifact itself never lives in Git."""

    __tablename__ = "profile_sources"
    __table_args__ = (
        CheckConstraint(
            "content_sha256 IS NULL OR length(content_sha256) = 64", name="content_sha256_length"
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ProfileSourceKind] = mapped_column(
        str_enum(ProfileSourceKind, "profile_source_kind")
    )
    original_filename: Mapped[str | None] = mapped_column(String(255))
    # Opaque pointer into private runtime storage (not a repository path).
    storage_ref: Mapped[str | None] = mapped_column(String(1024))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped[Profile] = relationship(back_populates="sources")
    facts: Mapped[list["ProfileFact"]] = relationship(
        back_populates="profile_source", passive_deletes=True
    )


class ProfileFact(IdMixin, TimestampMixin, Base):
    """A structured fact with provenance. Not used by hard eligibility (see ADR-006)."""

    __tablename__ = "profile_facts"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        CheckConstraint(
            "extraction_method <> 'ai_inference' OR extractor_name IS NOT NULL",
            name="ai_inference_has_extractor",
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    profile_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_sources.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[FactCategory] = mapped_column(str_enum(FactCategory, "fact_category"))
    fact_key: Mapped[str] = mapped_column(String(100))
    value: Mapped[Any] = mapped_column(JSON)
    source_kind: Mapped[ProfileSourceKind] = mapped_column(
        str_enum(ProfileSourceKind, "fact_source_kind")
    )
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        str_enum(ExtractionMethod, "fact_extraction_method")
    )
    extractor_name: Mapped[str | None] = mapped_column(String(100))
    extractor_version: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    verified_by_user: Mapped[bool] = mapped_column(default=False, server_default=false())

    profile: Mapped[Profile] = relationship(back_populates="facts")
    profile_source: Mapped[ProfileSource | None] = relationship(back_populates="facts")
