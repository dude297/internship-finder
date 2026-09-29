"""The Match Profile (ADR-010 §5): fit preferences on `profiles` plus manual profile facts.

A save replaces only the facts this feature owns (manual, `match_profile.` key, the six
categories below) and then runs one catalog evaluation pass. Facts from any other source
(parsers, AI, résumé, GitHub) are never touched.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ExtractionMethod, FactCategory, ProfileSourceKind
from app.models import Profile, ProfileFact
from app.repositories import CatalogEvaluation, get_profile
from app.schemas.profile import MatchItem, MatchProfile
from app.services.opportunities import evaluate_all

KEY_PREFIX = "match_profile."
# Match Profile list field → fact category, in stored order.
TERM_FIELDS = {"skills": FactCategory.SKILL, "courses": FactCategory.COURSE}
ITEM_FIELDS = {
    "projects": FactCategory.PROJECT,
    "research": FactCategory.RESEARCH,
    "activities": FactCategory.ACTIVITY,
    "experience": FactCategory.EXPERIENCE,
}
PREFERENCE_FIELDS = (
    "interests",
    "preferred_locations",
    "remote_preference",
    "availability_start",
    "availability_end",
)


def _owned_facts(db: Session, profile: Profile) -> list[ProfileFact]:
    return list(
        db.scalars(
            select(ProfileFact)
            .where(
                ProfileFact.profile_id == profile.id,
                ProfileFact.source_kind == ProfileSourceKind.MANUAL,
                ProfileFact.extraction_method == ExtractionMethod.MANUAL,
                ProfileFact.category.in_([*TERM_FIELDS.values(), *ITEM_FIELDS.values()]),
                ProfileFact.fact_key.startswith(KEY_PREFIX, autoescape=True),
            )
            .order_by(ProfileFact.fact_key)
        ).all()
    )


def _desired(body: MatchProfile) -> list[tuple[FactCategory, dict[str, Any]]]:
    facts: list[tuple[FactCategory, dict[str, Any]]] = []
    for field, category in TERM_FIELDS.items():
        facts += [(category, {"name": name}) for name in getattr(body, field)]
    for field, category in ITEM_FIELDS.items():
        items: list[MatchItem] = getattr(body, field)
        facts += [(category, item.model_dump()) for item in items]
    return facts


def read_match_profile(db: Session) -> MatchProfile:
    profile = get_profile(db)
    if profile is None:
        return MatchProfile()
    lists: dict[FactCategory, list[Any]] = {}
    for fact in _owned_facts(db, profile):
        lists.setdefault(fact.category, []).append(fact.value)
    return MatchProfile.model_validate(
        {
            **{field: [v["name"] for v in lists.get(c, [])] for field, c in TERM_FIELDS.items()},
            **{field: lists.get(c, []) for field, c in ITEM_FIELDS.items()},
            **{field: getattr(profile, field) for field in PREFERENCE_FIELDS},
            "interests": profile.interests or [],
            "preferred_locations": profile.preferred_locations or [],
        }
    )


def save_match_profile(db: Session, body: MatchProfile) -> CatalogEvaluation:
    """Replace the Match Profile atomically (creating the profile row if needed), then run one
    catalog pass in the same transaction. Unchanged facts aren't rewritten, and unchanged
    opportunities get no new evaluation row."""
    profile = get_profile(db)
    if profile is None:
        profile = Profile()
        db.add(profile)
        db.flush()
    for field in PREFERENCE_FIELDS:
        setattr(profile, field, getattr(body, field))
    profile.interests = body.interests or None
    profile.preferred_locations = body.preferred_locations or None

    desired = _desired(body)
    owned = _owned_facts(db, profile)
    if [(f.category, f.value) for f in owned] != desired:
        for fact in owned:
            db.delete(fact)
        db.add_all(
            ProfileFact(
                profile_id=profile.id,
                category=category,
                fact_key=f"{KEY_PREFIX}{position:03d}",
                value=value,
                source_kind=ProfileSourceKind.MANUAL,
                extraction_method=ExtractionMethod.MANUAL,
                verified_by_user=True,
            )
            for position, (category, value) in enumerate(desired)
        )
    db.flush()
    return evaluate_all(db, profile)
