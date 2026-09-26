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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import (
    ExtractionMethod,
    OpportunitySourceType,
    OpportunityType,
    RemoteMode,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)


def _seen_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Opportunity(IdMixin, TimestampMixin, Base):
    """Canonical, source-independent opportunity record."""

    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="end_not_before_start",
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="last_seen_not_before_first"),
    )

    title: Mapped[str] = mapped_column(String(300))
    organization: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    opportunity_type: Mapped[OpportunityType] = mapped_column(
        str_enum(OpportunityType, "opportunity_type")
    )
    application_url: Mapped[str | None] = mapped_column(String(2048))
    location: Mapped[str | None] = mapped_column(String(200))
    remote_mode: Mapped[RemoteMode | None] = mapped_column(str_enum(RemoteMode, "remote_mode"))
    application_deadline: Mapped[date | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    # Whether `requirements` is the full set of hard requirements (see ELIG-REQ-000).
    requirements_assessment_status: Mapped[RequirementsAssessmentStatus] = mapped_column(
        str_enum(RequirementsAssessmentStatus, "requirements_assessment_status"),
        default=RequirementsAssessmentStatus.UNASSESSED,
        server_default=RequirementsAssessmentStatus.UNASSESSED.value,
    )
    first_seen_at: Mapped[datetime] = _seen_at()
    last_seen_at: Mapped[datetime] = _seen_at()

    source_records: Mapped[list["OpportunitySourceRecord"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
    requirements: Mapped[list["OpportunityRequirement"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )


class OpportunitySourceRecord(IdMixin, Base):
    """Where a canonical opportunity was seen. One opportunity may have many source records."""

    __tablename__ = "opportunity_source_records"
    __table_args__ = (
        # NULL external IDs don't collide (SQL NULLs are distinct), so ID-less sources still fit.
        UniqueConstraint("source_name", "external_id"),
        CheckConstraint("last_seen_at >= first_seen_at", name="last_seen_not_before_first"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    source_name: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[OpportunitySourceType] = mapped_column(
        str_enum(OpportunitySourceType, "source_type")
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    raw_payload: Mapped[Any] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = _seen_at()
    last_seen_at: Mapped[datetime] = _seen_at()

    opportunity: Mapped[Opportunity] = relationship(back_populates="source_records")


class OpportunityRequirement(IdMixin, TimestampMixin, Base):
    """A structured requirement. `value` shape per type: app.opportunities.eligibility.schemas."""

    __tablename__ = "opportunity_requirements"
    __table_args__ = (
        CheckConstraint(
            "(applies_at = 'explicit_date' AND reference_date IS NOT NULL)"
            " OR (applies_at <> 'explicit_date' AND reference_date IS NULL)",
            name="reference_date_iff_explicit",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        CheckConstraint(
            "extraction_method <> 'ai_inference' OR extractor_name IS NOT NULL",
            name="ai_inference_has_extractor",
        ),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    requirement_type: Mapped[RequirementType] = mapped_column(
        str_enum(RequirementType, "requirement_type")
    )
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    applies_at: Mapped[RequirementAppliesAt] = mapped_column(
        str_enum(RequirementAppliesAt, "applies_at"),
        default=RequirementAppliesAt.PROGRAM_START,
        server_default=RequirementAppliesAt.PROGRAM_START.value,
    )
    reference_date: Mapped[date | None]
    source_text: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        str_enum(ExtractionMethod, "requirement_extraction_method")
    )
    extractor_name: Mapped[str | None] = mapped_column(String(100))
    extractor_version: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)

    opportunity: Mapped[Opportunity] = relationship(back_populates="requirements")
