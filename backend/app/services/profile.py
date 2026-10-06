"""The single canonical profile (single-user, ADR-007)."""

from sqlalchemy.orm import Session

from app.models import Profile
from app.opportunities.eligibility.schemas import ProfileInput
from app.repositories import get_profile
from app.schemas.profile import ProfileBody
from app.services.opportunities import evaluate_all

WORK_AUTH_FIELDS = frozenset(
    {
        "work_authorized_us",
        "needs_sponsorship_now",
        "needs_sponsorship_future",
        "us_citizen",
        "us_permanent_resident",
        "us_person_export_control",
        "active_security_clearance",
    }
)


def save_profile(db: Session, body: ProfileBody) -> tuple[Profile, int]:
    """Create or replace the profile. If an eligibility input changed (the fields of
    ProfileInput), re-evaluate every opportunity in the same transaction; returns the count.

    Only opportunities whose inputs changed get a new evaluation row (see evaluate_all)."""
    profile = get_profile(db)
    before = ProfileInput.model_validate(profile) if profile else None
    if profile is None:
        profile = Profile()
        db.add(profile)
    # A body without the work-authorization answers (an older client) keeps the stored ones
    # instead of clearing them (ADR-026).
    keep = WORK_AUTH_FIELDS - body.model_fields_set
    for name, value in body.model_dump().items():
        if name in keep:
            continue
        setattr(profile, name, value)
    db.flush()
    if ProfileInput.model_validate(profile) == before:
        return profile, 0
    return profile, evaluate_all(db, profile).evaluated
