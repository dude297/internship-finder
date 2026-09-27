from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.repositories import get_profile
from app.schemas.profile import ProfileBody, ProfileResponse, ProfileSaveResponse
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
