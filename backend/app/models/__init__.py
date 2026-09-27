"""ORM models. Importing this package registers every table on `Base.metadata`."""

from app.db.base import Base
from app.models.application import Application
from app.models.auth import AuthSession, AuthUser
from app.models.evaluation import EligibilityRuleResult, OpportunityEvaluation
from app.models.ingestion import IngestionRun, IngestionRunError, IngestionSource
from app.models.opportunity import (
    Opportunity,
    OpportunityIdentifier,
    OpportunityRequirement,
    OpportunitySourceRecord,
)
from app.models.profile import Profile, ProfileFact, ProfileSource

__all__ = [
    "Application",
    "AuthSession",
    "AuthUser",
    "Base",
    "EligibilityRuleResult",
    "IngestionRun",
    "IngestionRunError",
    "IngestionSource",
    "Opportunity",
    "OpportunityEvaluation",
    "OpportunityIdentifier",
    "OpportunityRequirement",
    "OpportunitySourceRecord",
    "Profile",
    "ProfileFact",
    "ProfileSource",
]
