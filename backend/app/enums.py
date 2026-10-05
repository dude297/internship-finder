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


class FactReviewState(StrEnum):
    """Owner review of a deterministic proposal: a profile fact (ADR-011; only accepted facts
    feed fit scoring) or an opportunity requirement candidate (ADR-012; only accepted candidates
    become canonical requirements)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    RESEARCH = "research"
    FELLOWSHIP = "fellowship"
    SUMMER_PROGRAM = "summer_program"
    SCHOLARSHIP = "scholarship"
    COMPETITION = "competition"
    VOLUNTEER = "volunteer"
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
    # The repository's curated program registry (ADR-014 §5): its own provenance, never `manual`.
    CURATED_REGISTRY = "curated_registry"
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


class RequirementsAssessmentStatus(StrEnum):
    """How completely an opportunity's hard requirements are represented as requirement rows.

    Never inferred from the number of rows: zero rows is legitimate only when `complete`.
    """

    UNASSESSED = "unassessed"  # not (sufficiently) assessed yet; rows, if any, are incidental
    PARTIAL = "partial"  # some requirements represented; others may exist
    COMPLETE = "complete"  # every hard requirement is represented


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    NEEDS_VERIFICATION = "needs_verification"
    INELIGIBLE = "ineligible"


class RemotePreference(StrEnum):
    """The owner's work-mode preference. A fit input only (ADR-010), never eligibility."""

    NO_PREFERENCE = "no_preference"
    REMOTE_PREFERRED = "remote_preferred"
    HYBRID_PREFERRED = "hybrid_preferred"
    ONSITE_PREFERRED = "onsite_preferred"
    REMOTE_ONLY = "remote_only"


class ApplicationStatus(StrEnum):
    """The owner's application state for one opportunity. Any status may follow any other:
    real processes skip steps and reopen, so no transition rules are enforced."""

    SAVED = "saved"
    APPLYING = "applying"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class IngestionSourceKind(StrEnum):
    """Automated source types (ADR-008). Each kind has one adapter with hard-coded hosts."""

    COMMUNITY_FEED = "community_feed"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    # Milestone 8.1 (ADR-015 §7): documented, keyless public job-board APIs.
    WORKABLE = "workable"
    PINPOINT = "pinpoint"
    # Built-in: the repository's program registry file (ADR-014 §5); no network.
    CURATED_REGISTRY = "curated_registry"


class SourceRegion(StrEnum):
    """Lever hosts postings on a global and an EU API."""

    GLOBAL = "global"
    EU = "eu"


class SourceScope(StrEnum):
    """Which provider items a source admits (ADR-010 §10). The built-in feed is always `all`."""

    ALL = "all"
    INTERNSHIPS_ONLY = "internships_only"  # title-based internship filter


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"  # complete snapshot, every item processed
    PARTIAL = "partial"  # some items failed; unseen records are not closed
    FAILED = "failed"  # nothing usable fetched; nothing changed
    NO_CHANGE = "no_change"  # HTTP 304


class IngestionStage(StrEnum):
    FETCH = "fetch"
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    IDENTIFY = "identify"
    PERSIST = "persist"
