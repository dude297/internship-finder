"""Fit scoring (ADR-010): the single public entry point is `score_fit`."""

from app.opportunities.scoring.config import SCORING_VERSION
from app.opportunities.scoring.engine import score_fit
from app.opportunities.scoring.schemas import (
    FitOpportunityInput,
    FitProfileInput,
    NamedItem,
    ScoreBreakdown,
)

__all__ = [
    "SCORING_VERSION",
    "FitOpportunityInput",
    "FitProfileInput",
    "NamedItem",
    "ScoreBreakdown",
    "score_fit",
]
