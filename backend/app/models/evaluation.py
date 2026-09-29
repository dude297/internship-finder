import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, str_enum
from app.enums import EligibilityStatus


class OpportunityEvaluation(IdMixin, Base):
    """One evaluation of an opportunity for a profile: eligibility and, since scoring v1, fit
    (ADR-010). Rows are history: a re-evaluation adds a row rather than overwriting. Rows from
    before scoring v1 have NULL fit columns."""

    __tablename__ = "opportunity_evaluations"
    __table_args__ = (
        Index(
            "ix_opportunity_evaluations_pair_evaluated_at",
            "profile_id",
            "opportunity_id",
            "evaluated_at",
        ),
        CheckConstraint("fit_score IS NULL OR fit_score BETWEEN 0 AND 100", name="fit_score_range"),
        CheckConstraint(
            "fit_input_fingerprint IS NULL OR length(fit_input_fingerprint) = 64",
            name="fit_input_fingerprint_length",
        ),
        CheckConstraint(
            "(fit_score IS NULL) = (scoring_version IS NULL)"
            " AND (fit_score IS NULL) = (score_breakdown IS NULL)"
            " AND (fit_score IS NULL) = (fit_input_fingerprint IS NULL)",
            name="fit_fields_together",
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
    # SHA-256 of the canonical eligibility inputs (ADR-008 §9). Automatic evaluation skips when
    # the latest evaluation has the same fingerprint. NULL for evaluations before Milestone 3.
    input_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # Fit (ADR-010). Shape of score_breakdown: app.opportunities.scoring.schemas.ScoreBreakdown.
    fit_score: Mapped[int | None]
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    scoring_version: Mapped[str | None] = mapped_column(String(20))
    fit_input_fingerprint: Mapped[str | None] = mapped_column(String(64))

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
