"""API endpoints for user lifestyle profile management.

Provides GET and PUT for /api/profile to read and update
the user's lifestyle profile (employment status, commute method, vehicle type).

Requirements covered: 15.1, 15.4, 15.5
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.profile import LifestyleProfileInput, LifestyleProfileResponse
from app.services.profile_service import (
    ProfileValidationError,
    get_profile,
    update_profile,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _get_current_user(db: Session = Depends(get_db)) -> User:
    """Get or create the current user.

    In a real app this would use authentication. For now, we use user_id=1.
    """
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, timezone="UTC")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("", response_model=LifestyleProfileResponse)
def get_profile_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> LifestyleProfileResponse:
    """Return the current user's lifestyle profile.

    Returns 404 if the user has not yet completed profile onboarding.
    """
    try:
        profile = get_profile(db=db, user_id=user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found.")

    if not profile.profile_completed:
        raise HTTPException(
            status_code=404,
            detail="Profile not set. Please complete profile onboarding.",
        )

    return profile


@router.put("", response_model=LifestyleProfileResponse)
def update_profile_endpoint(
    request: LifestyleProfileInput,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> LifestyleProfileResponse:
    """Create or update the user's lifestyle profile.

    Validates input, stores profile data, and triggers weight recomputation.
    Returns 422 on validation errors, 404 if user not found.
    """
    try:
        profile = update_profile(db=db, user_id=user.id, profile_input=request)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found.")
    except ProfileValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return profile
