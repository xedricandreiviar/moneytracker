"""CategoryWeightService for managing per-user budget category weight allocations.

Handles deriving default weights from the Weight_Rules_Table based on user
Lifestyle_Profile, persisting weights, manual overrides with proportional
redistribution, and validation that all weights sum to exactly 100%.

Uses Decimal arithmetic throughout to avoid floating-point precision errors.

Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.category_weight import CategoryWeight
from app.models.user import User
from app.services.weight_rules import get_weights_for_profile

logger = logging.getLogger(__name__)

# The exact target sum for all category weights
TARGET_SUM = Decimal("100.00")


class WeightValidationError(Exception):
    """Raised when category weights fail validation (sum != 100%)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class WeightOverrideError(Exception):
    """Raised when a weight override cannot be applied (e.g., all others are manual)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_weights(weights: List[CategoryWeight]) -> bool:
    """Assert that all category weight entries sum to exactly 100.00%.

    Args:
        weights: List of CategoryWeight entries for a user.

    Returns:
        True if valid.

    Raises:
        WeightValidationError: If the sum does not equal 100.00.
    """
    total = sum(w.weight_percentage for w in weights)
    if total != TARGET_SUM:
        raise WeightValidationError(
            f"Category weights must sum to exactly 100.00%, got {total}%."
        )
    return True


def derive_defaults(
    employment_status: Optional[str],
    commute_method: Optional[str],
    vehicle_type: Optional[str] = None,
) -> Dict[str, Decimal]:
    """Pure function: derive default category weight percentages from profile answers.

    Looks up the Weight_Rules_Table using the profile answers and returns a
    dictionary mapping category names to their default weight percentages.
    All values sum to exactly 100.00.

    Args:
        employment_status: User's employment status (student, working, both).
        commute_method: User's commute method.
        vehicle_type: User's vehicle type (only when commute_method is own_vehicle).

    Returns:
        Dict mapping category_name → Decimal weight percentage summing to 100.00.
    """
    return get_weights_for_profile(
        employment_status=employment_status or "working",
        commute_method=commute_method or "none_remote",
        vehicle_type=vehicle_type,
    )


def get_weights(db: Session, user_id: int) -> List[CategoryWeight]:
    """Get all CategoryWeight entries for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        List of CategoryWeight entries for the user.
    """
    return (
        db.query(CategoryWeight)
        .filter(CategoryWeight.user_id == user_id)
        .order_by(CategoryWeight.category_name)
        .all()
    )


def recompute_weights(db: Session, user_id: int) -> List[CategoryWeight]:
    """Recompute category weights based on the user's current Lifestyle_Profile.

    Fetches the user's profile, derives defaults from the Weight_Rules_Table,
    replaces non-manually-overridden entries with new defaults, and redistributes
    to maintain the 100% sum constraint.

    If manually-overridden entries exist, their percentages are preserved and
    the remaining percentage is distributed among non-overridden categories
    proportionally according to the new defaults.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        The updated list of CategoryWeight entries.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User with id {user_id} not found.")

    # Derive new defaults from the user's profile
    defaults = derive_defaults(
        employment_status=user.employment_status.value if user.employment_status else None,
        commute_method=user.commute_method.value if user.commute_method else None,
        vehicle_type=user.vehicle_type.value if user.vehicle_type else None,
    )

    # Get existing weights
    existing_weights = get_weights(db, user_id)
    existing_map: Dict[str, CategoryWeight] = {
        w.category_name: w for w in existing_weights
    }

    # Determine manually overridden entries and their total
    manual_total = Decimal("0.00")
    manual_categories: set = set()
    for w in existing_weights:
        if w.is_manual_override:
            manual_total += w.weight_percentage
            manual_categories.add(w.category_name)

    # Calculate available percentage for non-manual categories
    available = TARGET_SUM - manual_total

    # Get non-manual categories from defaults
    non_manual_defaults = {
        cat: pct for cat, pct in defaults.items() if cat not in manual_categories
    }

    # Proportionally distribute the available percentage among non-manual categories
    non_manual_default_total = sum(non_manual_defaults.values())
    distributed: Dict[str, Decimal] = {}

    if non_manual_default_total > Decimal("0"):
        for cat, pct in non_manual_defaults.items():
            ratio = pct / non_manual_default_total
            distributed[cat] = (ratio * available).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    elif non_manual_defaults:
        # If all defaults are 0, distribute equally
        equal_share = (available / Decimal(str(len(non_manual_defaults)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for cat in non_manual_defaults:
            distributed[cat] = equal_share

    # Fix rounding errors: adjust the last non-manual category
    if distributed:
        distributed_total = sum(distributed.values())
        rounding_error = available - distributed_total
        if rounding_error != Decimal("0"):
            # Adjust the last category alphabetically
            last_cat = sorted(distributed.keys())[-1]
            distributed[last_cat] += rounding_error

    # Apply changes: update existing or create new entries
    all_categories = set(defaults.keys()) | manual_categories
    result_weights: List[CategoryWeight] = []

    for category_name in sorted(all_categories):
        if category_name in existing_map:
            cw = existing_map[category_name]
            if category_name not in manual_categories:
                cw.weight_percentage = distributed.get(category_name, Decimal("0.00"))
                cw.is_manual_override = False
            result_weights.append(cw)
        else:
            # Create new entry
            new_weight = CategoryWeight(
                user_id=user_id,
                category_name=category_name,
                weight_percentage=distributed.get(category_name, Decimal("0.00")),
                is_manual_override=False,
            )
            db.add(new_weight)
            result_weights.append(new_weight)

    # Remove entries that are no longer in the category set
    for category_name, cw in existing_map.items():
        if category_name not in all_categories:
            db.delete(cw)

    db.commit()
    for w in result_weights:
        db.refresh(w)

    # Validate the final result
    validate_weights(result_weights)

    return result_weights


def override_weight(
    db: Session,
    user_id: int,
    category_name: str,
    new_percentage: Decimal,
) -> List[CategoryWeight]:
    """Manually override a single category's weight percentage.

    Sets the specified category to the new percentage, marks it as manually
    overridden, and redistributes remaining non-overridden categories
    proportionally so that all weights continue to sum to exactly 100%.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_name: The category to override.
        new_percentage: The new weight percentage (Decimal, 0-100).

    Returns:
        The updated list of CategoryWeight entries.

    Raises:
        WeightOverrideError: If the override cannot be applied (e.g., all other
            categories are already manually overridden, or percentage is invalid).
        ValueError: If the category is not found for this user.
    """
    # Validate new_percentage range
    if new_percentage < Decimal("0") or new_percentage > TARGET_SUM:
        raise WeightOverrideError(
            f"Weight percentage must be between 0 and 100, got {new_percentage}."
        )

    existing_weights = get_weights(db, user_id)
    if not existing_weights:
        raise ValueError(f"No category weights found for user {user_id}.")

    # Find the target category
    target: Optional[CategoryWeight] = None
    others: List[CategoryWeight] = []
    for w in existing_weights:
        if w.category_name == category_name:
            target = w
        else:
            others.append(w)

    if target is None:
        raise ValueError(
            f"Category '{category_name}' not found for user {user_id}."
        )

    # Find non-overridden others (excluding the target category)
    non_overridden_others = [w for w in others if not w.is_manual_override]

    # Edge case: all other categories are manually overridden
    if not non_overridden_others:
        raise WeightOverrideError(
            "Cannot override: all other categories are already manually overridden. "
            "No categories available for redistribution."
        )

    # Calculate remaining percentage to distribute
    remaining = TARGET_SUM - new_percentage

    # Sum of all OTHER categories' current percentages (manual + non-manual)
    manual_others_total = sum(
        w.weight_percentage for w in others if w.is_manual_override
    )

    # Available for non-overridden categories
    available_for_non_overridden = remaining - manual_others_total

    if available_for_non_overridden < Decimal("0"):
        raise WeightOverrideError(
            f"Cannot set {category_name} to {new_percentage}%: "
            f"manually overridden categories already total {manual_others_total}%, "
            f"which exceeds the remaining {remaining}%."
        )

    # Redistribute proportionally among non-overridden others
    non_overridden_total = sum(w.weight_percentage for w in non_overridden_others)
    distributed: Dict[str, Decimal] = {}

    if non_overridden_total > Decimal("0"):
        for w in non_overridden_others:
            ratio = w.weight_percentage / non_overridden_total
            distributed[w.category_name] = (
                ratio * available_for_non_overridden
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        # All non-overridden others are at 0; distribute equally
        equal_share = (
            available_for_non_overridden / Decimal(str(len(non_overridden_others)))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for w in non_overridden_others:
            distributed[w.category_name] = equal_share

    # Fix rounding errors
    if distributed:
        distributed_total = sum(distributed.values())
        rounding_error = available_for_non_overridden - distributed_total
        if rounding_error != Decimal("0"):
            last_cat = sorted(distributed.keys())[-1]
            distributed[last_cat] += rounding_error

    # Apply the override
    target.weight_percentage = new_percentage
    target.is_manual_override = True

    # Apply redistribution
    for w in non_overridden_others:
        w.weight_percentage = distributed[w.category_name]

    db.commit()

    # Refresh and validate
    all_weights = get_weights(db, user_id)
    validate_weights(all_weights)

    return all_weights
