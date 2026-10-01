import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import (
    ExtractionMethod,
    FactReviewState,
    OpportunitySourceType,
    OpportunityType,
    RemoteMode,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.ingestion import IngestionSource


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
        CheckConstraint(
            "requirement_extraction_fingerprint IS NULL"
            " OR length(requirement_extraction_fingerprint) = 64",
            name="requirement_extraction_fingerprint_length",
        ),
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
    # When the source says the posting was published (never an ATS "updated" time). Discovery
    # sorting only; eligibility doesn't read it.
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # Set when the owner creates or edits it through the API. Sync never overwrites the canonical
    # fields or requirements of a curated opportunity (ADR-008 §8).
    manually_curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ADR-012 §6: set when a source update materially changed the posting text after the owner
    # had reviewed its requirements; cleared by the owner's next review. Display + filter only.
    requirements_stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ADR-012 §4: SHA-256 of (extractor name, version, extraction inputs) at the last candidate
    # extraction. NULL = never extracted. The catalog scan skips rows whose value is current.
    requirement_extraction_fingerprint: Mapped[str | None] = mapped_column(String(64))

    source_records: Mapped[list["OpportunitySourceRecord"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
    identifiers: Mapped[list["OpportunityIdentifier"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
    requirements: Mapped[list["OpportunityRequirement"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
    requirement_candidates: Mapped[list["OpportunityRequirementCandidate"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
    application: Mapped["Application | None"] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )


class OpportunitySourceRecord(IdMixin, Base):
    """Where a canonical opportunity was seen. One opportunity may have many source records."""

    __tablename__ = "opportunity_source_records"
    __table_args__ = (
        # NULL external IDs don't collide (SQL NULLs are distinct), so ID-less sources still fit.
        UniqueConstraint("source_name", "external_id"),
        CheckConstraint("last_seen_at >= first_seen_at", name="last_seen_not_before_first"),
        CheckConstraint("is_active = (closed_at IS NULL)", name="closed_iff_inactive"),
        CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64", name="content_hash_length"
        ),
        Index(
            "ix_opportunity_source_records_ingestion_source_id_is_active",
            "ingestion_source_id",
            "is_active",
        ),
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
    # Automated records only (NULL for manual provenance). Sources are never deleted.
    ingestion_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_sources.id")
    )
    # Present in the source's latest complete successful snapshot. Closed records are kept.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SHA-256 of the normalized item (raw payload included): unchanged items skip all writes
    # except last-seen.
    content_hash: Mapped[str | None] = mapped_column(String(64))

    opportunity: Mapped[Opportunity] = relationship(back_populates="source_records")
    ingestion_source: Mapped["IngestionSource | None"] = relationship()


class OpportunityIdentifier(IdMixin, Base):
    """A deterministic identity of a canonical opportunity, shared across sources (ADR-008 §6).
    Unique per (namespace, value), so two opportunities can never claim the same identity."""

    __tablename__ = "opportunity_identifiers"
    __table_args__ = (UniqueConstraint("namespace", "value"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    namespace: Mapped[str] = mapped_column(String(32))
    # Bounded so the unique btree entry stays well under PostgreSQL's index row limit.
    value: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    opportunity: Mapped[Opportunity] = relationship(back_populates="identifiers")


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


class OpportunityRequirementCandidate(IdMixin, TimestampMixin, Base):
    """A deterministic requirement proposal awaiting (or past) owner review (ADR-012).

    Never read by eligibility: only canonical `opportunity_requirements` are. Identity is the
    semantic key (type, normalized value, applies_at, reference_date), never position, source
    text, or IDs, so re-extraction can't resurrect a rejected or duplicate an accepted proposal.
    The row keeps the original proposal even when the owner edits the value on accept; the
    edited value lives only on the linked canonical requirement."""

    __tablename__ = "opportunity_requirement_candidates"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "semantic_key"),
        CheckConstraint("length(semantic_key) = 64", name="semantic_key_length"),
        CheckConstraint(
            "(applies_at = 'explicit_date' AND reference_date IS NOT NULL)"
            " OR (applies_at <> 'explicit_date' AND reference_date IS NULL)",
            name="reference_date_iff_explicit",
        ),
        CheckConstraint(
            "accepted_requirement_id IS NULL OR review_state = 'accepted'",
            name="linked_only_when_accepted",
        ),
    )

    # Indexed by the (opportunity_id, semantic_key) unique constraint.
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    semantic_key: Mapped[str] = mapped_column(String(64))
    requirement_type: Mapped[RequirementType] = mapped_column(
        str_enum(RequirementType, "candidate_requirement_type")
    )
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    applies_at: Mapped[RequirementAppliesAt] = mapped_column(
        str_enum(RequirementAppliesAt, "candidate_applies_at")
    )
    reference_date: Mapped[date | None]
    # Bounded evidence excerpt (ADR-012 §5). Plain text; rendered only as text.
    source_text: Mapped[str] = mapped_column(String(500))
    extractor_name: Mapped[str] = mapped_column(String(100))
    extractor_version: Mapped[str] = mapped_column(String(50))
    review_state: Mapped[FactReviewState] = mapped_column(
        str_enum(FactReviewState, "candidate_review_state")
    )
    # Whether the latest extraction of the current posting text proposed it. Pending candidates
    # that stop being proposed are deleted; reviewed ones are kept with is_current = false.
    is_current: Mapped[bool] = mapped_column(default=True, server_default=true())
    # The canonical requirement created on accept. SET NULL if the owner later deletes it.
    accepted_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_requirements.id", ondelete="SET NULL"), index=True
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="requirement_candidates")
