"""The single canonical profile (single-user, ADR-007)."""

from sqlalchemy.orm import Session

from app.models import Profile
from app.opportunities.eligibility.schemas import ProfileInput
from app.repositories import get_profile
from app.schemas.profile import ProfileBody
from app.services.opportunities import evaluate_all


def save_profile(db: Session, body: ProfileBody) -> tuple[Profile, int]:
    """Create or replace the profile. If an eligibility input changed (the fields of
    ProfileInput), re-evaluate every opportunity in the same transaction; returns the count.

    Only opportunities whose inputs changed get a new evaluation row (see evaluate_all)."""
    profile = get_profile(db)
    before = ProfileInput.model_validate(profile) if profile else None
    if profile is None:
        profile = Profile()
        db.add(profile)
    for name, value in body.model_dump().items():
        setattr(profile, name, value)
    db.flush()
    if ProfileInput.model_validate(profile) == before:
        return profile, 0
    return profile, evaluate_all(db, profile).evaluated
