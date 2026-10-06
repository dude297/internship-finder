import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import ApplicationEventType, ApplicationStatus
from app.models.opportunity import Opportunity


class Application(IdMixin, TimestampMixin, Base):
    """The owner's application tracking for one opportunity. Single-user, so at most one row per
    opportunity. Never read by eligibility."""

    __tablename__ = "applications"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus, "application_status")
    )
    submitted_on: Mapped[date | None]
    # Private runtime data.
    notes: Mapped[str | None] = mapped_column(Text)
    # ADR-020: the owner's follow-up reminders; read only by the Action Inbox.
    next_action: Mapped[str | None] = mapped_column(String(200))
    next_action_due: Mapped[date | None]
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ADR-025: when the application was actually submitted. Set once on the first move to
    # `applied`; the owner may correct it and a manual value is never overwritten.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opportunity: Mapped[Opportunity] = relationship(back_populates="application")


class ApplicationEvent(IdMixin, Base):
    """ADR-025: append-only history of meaningful application changes. No rows exist for changes
    made before the feature shipped; history is never reconstructed."""

    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint("length(metadata_json::text) <= 2000", name="metadata_bounded"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[ApplicationEventType] = mapped_column(
        str_enum(ApplicationEventType, "application_event_type")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        str_enum(ApplicationStatus, "application_event_from_status")
    )
    to_status: Mapped[ApplicationStatus | None] = mapped_column(
        str_enum(ApplicationStatus, "application_event_to_status")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
