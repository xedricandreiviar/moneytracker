"""API endpoints for category weight management.

Provides GET /api/weights, PUT /api/weights/{category_name},
and POST /api/weights/reset.

Requirements: 16.1, 16.4, 16.5, 16.6
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.weight import (
    CategoryWeightOverrideRequest,
    CategoryWeightResponse,
    WeightListResponse,
)
from app.services.category_weight_service import (
    WeightOverrideError,
    get_weights,
    override_weight,
    recompute_weights,
)

router = APIRouter(prefix="/api/weights", tags=["weights"])


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


def _weights_to_response(weights) -> WeightListResponse:
    """Convert a list of CategoryWeight model instances to a WeightListResponse."""
    weight_responses = [
        CategoryWeightResponse(
            category_name=w.category_name,
            weight_percentage=w.weight_percentage,
            is_manual_override=w.is_manual_override,
        )
        for w in weights
    ]
    total = sum(w.weight_percentage for w in weights)
    return WeightListResponse(weights=weight_responses, total_percentage=total)


@router.get("", response_model=WeightListResponse)
def get_weights_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> WeightListResponse | JSONResponse:
    """Get all category weight entries for the current user.

    Returns 400 if the user's profile has not been completed
    (weights cannot be derived without a lifestyle profile).
    """
    if not user.profile_completed:
        return JSONResponse(
            status_code=400,
            content={"detail": "Profile not completed. Weights cannot be derived without a lifestyle profile."},
        )

    weights = get_weights(db=db, user_id=user.id)
    return _weights_to_response(weights)


@router.put("/{category_name}", response_model=WeightListResponse)
def override_weight_endpoint(
    category_name: str,
    request: CategoryWeightOverrideRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> WeightListResponse | JSONResponse:
    """Manually override a single category's weight percentage.

    Redistributes remaining non-overridden categories proportionally
    to maintain 100% total.

    Returns 400 if profile not completed.
    Returns 422 if override would leave no categories available for redistribution.
    Returns 404 if category not found for this user.
    """
    if not user.profile_completed:
        return JSONResponse(
            status_code=400,
            content={"detail": "Profile not completed. Weights cannot be derived without a lifestyle profile."},
        )

    try:
        updated_weights = override_weight(
            db=db,
            user_id=user.id,
            category_name=category_name,
            new_percentage=request.new_percentage,
        )
    except WeightOverrideError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": e.message},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _weights_to_response(updated_weights)


@router.post("/reset", response_model=WeightListResponse)
def reset_weights_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> WeightListResponse | JSONResponse:
    """Reset all weights to profile-derived defaults.

    Clears all manual overrides and recomputes weights from the
    Weight_Rules_Table based on the user's current lifestyle profile.

    Returns 400 if profile not completed.
    """
    if not user.profile_completed:
        return JSONResponse(
            status_code=400,
            content={"detail": "Profile not completed. Weights cannot be derived without a lifestyle profile."},
        )

    # Clear all manual override flags before recomputing
    existing_weights = get_weights(db=db, user_id=user.id)
    for w in existing_weights:
        w.is_manual_override = False
    db.commit()

    updated_weights = recompute_weights(db=db, user_id=user.id)
    return _weights_to_response(updated_weights)
