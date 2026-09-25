"""Enumerations shared by the ORM models and the domain logic.

Stored as VARCHAR + CHECK constraint (not native Postgres enums), so migrations and downgrades
don't have to manage enum types. Adding a value needs a migration that updates the CHECK.
"""

from enum import StrEnum


class EducationLevel(StrEnum):
    HIGH_SCHOOL = "high_school"
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"


class EducationPhase(StrEnum):
    """Where the user stands relative to an education level on a given date."""

    ENROLLED = "enrolled"
    # Finished the previous level, not yet started this one (e.g. "incoming undergraduate").
    INCOMING = "incoming"
    UNKNOWN = "unknown"


class ProfileSourceKind(StrEnum):
    MANUAL = "manual"
    RESUME = "resume"
    TRANSCRIPT = "transcript"
    COURSE_LIST = "course_list"
    PROJECT = "project"
    GITHUB = "github"
    USER_PREFERENCE = "user_preference"
    OTHER = "other"


class ExtractionMethod(StrEnum):
    MANUAL = "manual"
    DETERMINISTIC_PARSER = "deterministic_parser"
    AI_INFERENCE = "ai_inference"


class FactCategory(StrEnum):
    EDUCATION = "education"
    COURSE = "course"
    SKILL = "skill"
    PROJECT = "project"
    AWARD = "award"
    ACTIVITY = "activity"
    EXPERIENCE = "experience"
    RESEARCH = "research"
    PREFERENCE = "preference"
    OTHER = "other"


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    RESEARCH = "research"
    FELLOWSHIP = "fellowship"
    SUMMER_PROGRAM = "summer_program"
    SCHOLARSHIP = "scholarship"
    COMPETITION = "competition"
    OTHER = "other"


class RemoteMode(StrEnum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class OpportunitySourceType(StrEnum):
    PUBLIC_FEED = "public_feed"
    ATS = "ats"
    CAREER_PAGE = "career_page"
    BROWSER = "browser"
    MANUAL = "manual"
    OTHER = "other"


class RequirementType(StrEnum):
    MINIMUM_AGE = "minimum_age"
    EDUCATION = "education"
    CITIZENSHIP = "citizenship"
    WORK_AUTHORIZATION = "work_authorization"
    OTHER = "other"


class RequirementAppliesAt(StrEnum):
    """Which date a requirement is evaluated on."""

    APPLICATION = "application"  # the application deadline
    PROGRAM_START = "program_start"  # the opportunity start date
    EXPLICIT_DATE = "explicit_date"  # a date stated by the posting (requirement.reference_date)


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    NEEDS_VERIFICATION = "needs_verification"
    INELIGIBLE = "ineligible"
