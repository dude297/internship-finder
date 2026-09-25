"""ORM models. Importing this package registers every table on `Base.metadata`."""

from app.db.base import Base
from app.models.evaluation import EligibilityRuleResult, OpportunityEvaluation
from app.models.opportunity import Opportunity, OpportunityRequirement, OpportunitySourceRecord
from app.models.profile import Profile, ProfileFact, ProfileSource

__all__ = [
    "Base",
    "EligibilityRuleResult",
    "Opportunity",
    "OpportunityEvaluation",
    "OpportunityRequirement",
    "OpportunitySourceRecord",
    "Profile",
    "ProfileFact",
    "ProfileSource",
]
