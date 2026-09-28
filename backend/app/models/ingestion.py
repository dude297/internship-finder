import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import IngestionRunStatus, IngestionSourceKind, IngestionStage, SourceRegion

RUNNING_RUN_INDEX = "uq_ingestion_runs_one_running_per_source"


class IngestionSource(IdMixin, TimestampMixin, Base):
    """A configured automated source (ADR-008 §1). Safe configuration only: the adapter builds
    the URL from a hard-coded provider host and the validated identifier. No URL is stored."""

    __tablename__ = "ingestion_sources"
    __table_args__ = (
        UniqueConstraint("kind", "identifier", "region", postgresql_nulls_not_distinct=True),
        CheckConstraint("(kind = 'lever') = (region IS NOT NULL)", name="region_iff_lever"),
    )

    kind: Mapped[IngestionSourceKind] = mapped_column(
        str_enum(IngestionSourceKind, "ingestion_source_kind")
    )
    # Greenhouse board token, Lever site slug, or the built-in feed's key.
    identifier: Mapped[str] = mapped_column(String(64))
    region: Mapped[SourceRegion | None] = mapped_column(str_enum(SourceRegion, "source_region"))
    display_name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # HTTP validators for conditional requests.
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(100))

    @property
    def builtin(self) -> bool:
        """The application-owned discovery feed: it can be disabled but not re-pointed."""
        return self.kind is IngestionSourceKind.COMMUNITY_FEED

    @property
    def key(self) -> str:
        """Stable, human-readable key; also the `source_name` of its source records."""
        parts = [self.kind.value, *([self.region.value] if self.region else []), self.identifier]
        return ":".join(parts)


class IngestionRun(IdMixin, Base):
    """One sync of one source, with its counts. Never stores payloads or stack traces."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_source_id_started_at", "source_id", "started_at"),
        # The per-source sync guard (ADR-008 §4): at most one running run per source.
        Index(
            RUNNING_RUN_INDEX,
            "source_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_sources.id", ondelete="CASCADE")
    )
    status: Mapped[IngestionRunStatus] = mapped_column(
        str_enum(IngestionRunStatus, "ingestion_run_status")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The source's own snapshot time, when it states one (e.g. the feed's generated_at).
    source_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(default=0, server_default="0")
    normalized_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(default=0, server_default="0")
    deduplicated_count: Mapped[int] = mapped_column(default=0, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(default=0, server_default="0")
    closed_count: Mapped[int] = mapped_column(default=0, server_default="0")
    reactivated_count: Mapped[int] = mapped_column(default=0, server_default="0")
    invalid_count: Mapped[int] = mapped_column(default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(default=0, server_default="0")
    # Safe one-line summary for failed runs (no stack traces, headers, or payloads).
    error_summary: Mapped[str | None] = mapped_column(String(500))

    source: Mapped[IngestionSource] = relationship()
    errors: Mapped[list["IngestionRunError"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IngestionRunError.created_at",
    )


class IngestionRunError(IdMixin, Base):
    """A bounded, safe description of one problem in a run (at most 100 stored per run)."""

    __tablename__ = "ingestion_run_errors"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[IngestionStage] = mapped_column(str_enum(IngestionStage, "ingestion_stage"))
    code: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[IngestionRun] = relationship(back_populates="errors")
