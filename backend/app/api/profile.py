from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.repositories import get_profile
from app.schemas.profile import (
    MatchProfile,
    MatchProfileSaveResponse,
    ProfileBody,
    ProfileResponse,
    ProfileSaveResponse,
)
from app.services.match_profile import read_match_profile, save_match_profile
from app.services.profile import save_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def read_profile(db: DbSession) -> ProfileResponse:
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet.")
    return ProfileResponse.model_validate(profile)


@router.put("")
def put_profile(body: ProfileBody, db: DbSession) -> ProfileSaveResponse:
    """Create or replace the canonical profile; re-evaluates opportunities if eligibility
    inputs changed (same transaction)."""
    profile, reevaluated = save_profile(db, body)
    db.commit()
    return ProfileSaveResponse(
        profile=ProfileResponse.model_validate(profile), reevaluated_opportunities=reevaluated
    )


@router.get("/match")
def get_match_profile(db: DbSession) -> MatchProfile:
    """The Match Profile (fit inputs). Empty until saved."""
    return read_match_profile(db)


@router.put("/match")
def put_match_profile(body: MatchProfile, db: DbSession) -> MatchProfileSaveResponse:
    """Replace the Match Profile atomically and rescore the catalog once (ADR-010 §5, §9).
    Everything is saved together or not at all."""
    result = save_match_profile(db, body)
    db.commit()
    return MatchProfileSaveResponse(
        match_profile=read_match_profile(db),
        evaluated_opportunities=result.evaluated,
        unchanged_opportunities=result.unchanged,
    )
