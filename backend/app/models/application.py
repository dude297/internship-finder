import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, str_enum
from app.enums import ApplicationStatus
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

    opportunity: Mapped[Opportunity] = relationship(back_populates="application")
