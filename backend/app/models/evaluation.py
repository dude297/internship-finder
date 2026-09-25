import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, str_enum
from app.enums import EligibilityStatus


class OpportunityEvaluation(IdMixin, Base):
    """One eligibility evaluation of an opportunity for a profile. Rows are history: a
    re-evaluation adds a row rather than overwriting. Fit scoring columns are added with
    scoring v1 (ADR-006)."""

    __tablename__ = "opportunity_evaluations"
    __table_args__ = (
        Index(
            "ix_opportunity_evaluations_pair_evaluated_at",
            "profile_id",
            "opportunity_id",
            "evaluated_at",
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    eligibility_status: Mapped[EligibilityStatus] = mapped_column(
        str_enum(EligibilityStatus, "eligibility_status")
    )
    eligibility_rules_version: Mapped[str] = mapped_column(String(20))
    depends_on_projected_status: Mapped[bool]
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rule_results: Mapped[list["EligibilityRuleResult"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EligibilityRuleResult.position",
    )


class EligibilityRuleResult(IdMixin, Base):
    """The outcome of one rule for one requirement: the evaluation's explanation."""

    __tablename__ = "eligibility_rule_results"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_evaluations.id", ondelete="CASCADE"), index=True
    )
    # Kept if the requirement is later deleted; the rule result stays readable on its own.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_requirements.id", ondelete="SET NULL"), index=True
    )
    position: Mapped[int]
    rule_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[EligibilityStatus] = mapped_column(str_enum(EligibilityStatus, "rule_status"))
    reason: Mapped[str] = mapped_column(Text)
    reference_date: Mapped[date | None]
    depends_on_projected_status: Mapped[bool]
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    evaluation: Mapped[OpportunityEvaluation] = relationship(back_populates="rule_results")
