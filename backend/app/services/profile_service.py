"""ProfileService for managing user lifestyle profile data.

Handles reading and updating the Lifestyle_Profile (employment_status,
commute_method, vehicle_type) on the User record.

Requirements covered: 15.4, 15.5, 15.6
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import CommuteMethod, EmploymentStatus, User, VehicleType
from app.schemas.profile import LifestyleProfileInput, LifestyleProfileResponse

logger = logging.getLogger(__name__)


class ProfileValidationError(Exception):
    """Raised when profile input fails validation."""

    pass


def get_profile(db: Session, user_id: int) -> LifestyleProfileResponse:
    """Read the current lifestyle profile for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        LifestyleProfileResponse with current profile data.

    Raises:
        ValueError: If user not found.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    return LifestyleProfileResponse(
        employment_status=user.employment_status.value if user.employment_status else None,
        commute_method=user.commute_method.value if user.commute_method else None,
        vehicle_type=user.vehicle_type.value if user.vehicle_type else None,
        profile_completed=user.profile_completed,
    )


def update_profile(
    db: Session,
    user_id: int,
    profile_input: LifestyleProfileInput,
) -> LifestyleProfileResponse:
    """Validate and store lifestyle profile, then trigger weight recomputation.

    Validates that vehicle_type is None unless commute_method is 'own_vehicle'.
    On success, sets profile_completed=True and calls
    CategoryWeightService.recompute_weights(user_id).

    Args:
        db: Database session.
        user_id: The user's ID.
        profile_input: Validated profile input from the API layer.

    Returns:
        LifestyleProfileResponse with updated profile data.

    Raises:
        ValueError: If user not found.
        ProfileValidationError: If vehicle_type constraint is violated.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    # Validate: vehicle_type must be None unless commute_method = own_vehicle
    if profile_input.commute_method != "own_vehicle" and profile_input.vehicle_type is not None:
        raise ProfileValidationError(
            "vehicle_type must be None unless commute_method is 'own_vehicle'"
        )
    if profile_input.commute_method == "own_vehicle" and profile_input.vehicle_type is None:
        raise ProfileValidationError(
            "vehicle_type is required when commute_method is 'own_vehicle'"
        )

    # Update user record with profile data
    user.employment_status = EmploymentStatus(profile_input.employment_status)
    user.commute_method = CommuteMethod(profile_input.commute_method)
    user.vehicle_type = (
        VehicleType(profile_input.vehicle_type)
        if profile_input.vehicle_type
        else None
    )
    user.profile_completed = True

    db.commit()
    db.refresh(user)

    # Trigger category weight recomputation (Requirement 15.6)
    _recompute_weights(db, user_id)

    logger.info(
        "Profile updated for user %d: employment=%s, commute=%s, vehicle=%s",
        user_id,
        profile_input.employment_status,
        profile_input.commute_method,
        profile_input.vehicle_type,
    )

    return LifestyleProfileResponse(
        employment_status=user.employment_status.value if user.employment_status else None,
        commute_method=user.commute_method.value if user.commute_method else None,
        vehicle_type=user.vehicle_type.value if user.vehicle_type else None,
        profile_completed=user.profile_completed,
    )


def _recompute_weights(db: Session, user_id: int) -> None:
    """Call CategoryWeightService.recompute_weights if available.

    Uses lazy import to avoid circular dependencies since
    CategoryWeightService may not exist yet.
    """
    try:
        from app.services.category_weight_service import recompute_weights

        recompute_weights(db, user_id)
    except ImportError:
        logger.warning(
            "CategoryWeightService not available; skipping weight recomputation "
            "for user %d",
            user_id,
        )
