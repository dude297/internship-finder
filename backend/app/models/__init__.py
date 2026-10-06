"""ORM models. Importing this package registers every table on `Base.metadata`."""

from app.db.base import Base
from app.models.application import Application, ApplicationEvent
from app.models.auth import AuthSession, AuthUser
from app.models.evaluation import EligibilityRuleResult, OpportunityEvaluation
from app.models.ingestion import IngestionRun, IngestionRunError, IngestionSource
from app.models.opportunity import (
    Opportunity,
    OpportunityIdentifier,
    OpportunityRequirement,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from app.models.profile import Profile, ProfileFact, ProfileSource, ProfileSourceArtifact

__all__ = [
    "Application",
    "ApplicationEvent",
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
    "OpportunityRequirementCandidate",
    "OpportunitySourceRecord",
    "Profile",
    "ProfileFact",
    "ProfileSource",
    "ProfileSourceArtifact",
]
