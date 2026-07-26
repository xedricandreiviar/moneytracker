"""
Weight Rules Table — configurable category weight distributions based on
Lifestyle_Profile answers.

Key: Tuple[employment_status, commute_method, Optional[vehicle_type]]
Value: Dict[str, Decimal] mapping category_name → weight_percentage

All entries sum to exactly Decimal("100.00").
Numeric values are placeholders — structure is final, numbers are configurable.

Requirements: 16.2, 16.3
"""

from decimal import Decimal
from typing import Dict, Optional, Tuple

# Type alias for clarity
ProfileKey = Tuple[str, str, Optional[str]]
WeightDistribution = Dict[str, Decimal]

WEIGHT_RULES_TABLE: Dict[ProfileKey, WeightDistribution] = {
    # ─── Student Profiles ───────────────────────────────────────────────

    ("student", "public_transit", None): {
        "Savings": Decimal("20.00"),
        "Wants": Decimal("30.00"),
        "Transportation": Decimal("15.00"),
        "Food": Decimal("35.00"),
    },
    ("student", "own_vehicle", "motorcycle"): {
        "Savings": Decimal("15.00"),
        "Wants": Decimal("25.00"),
        "Transportation": Decimal("25.00"),
        "Food": Decimal("35.00"),
    },
    ("student", "own_vehicle", "car"): {
        "Savings": Decimal("10.00"),
        "Wants": Decimal("20.00"),
        "Transportation": Decimal("35.00"),
        "Food": Decimal("35.00"),
    },
    ("student", "walking_biking", None): {
        "Savings": Decimal("25.00"),
        "Wants": Decimal("35.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("35.00"),
    },
    ("student", "none_remote", None): {
        "Savings": Decimal("25.00"),
        "Wants": Decimal("35.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("35.00"),
    },

    # ─── Working Profiles ───────────────────────────────────────────────

    ("working", "public_transit", None): {
        "Savings": Decimal("30.00"),
        "Wants": Decimal("25.00"),
        "Transportation": Decimal("15.00"),
        "Food": Decimal("30.00"),
    },
    ("working", "own_vehicle", "motorcycle"): {
        "Savings": Decimal("25.00"),
        "Wants": Decimal("20.00"),
        "Transportation": Decimal("25.00"),
        "Food": Decimal("30.00"),
    },
    ("working", "own_vehicle", "car"): {
        "Savings": Decimal("20.00"),
        "Wants": Decimal("20.00"),
        "Transportation": Decimal("30.00"),
        "Food": Decimal("30.00"),
    },
    ("working", "walking_biking", None): {
        "Savings": Decimal("35.00"),
        "Wants": Decimal("30.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("30.00"),
    },
    ("working", "none_remote", None): {
        "Savings": Decimal("35.00"),
        "Wants": Decimal("30.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("30.00"),
    },

    # ─── Both (Student + Working) Profiles ──────────────────────────────

    ("both", "public_transit", None): {
        "Savings": Decimal("25.00"),
        "Wants": Decimal("25.00"),
        "Transportation": Decimal("15.00"),
        "Food": Decimal("35.00"),
    },
    ("both", "own_vehicle", "motorcycle"): {
        "Savings": Decimal("20.00"),
        "Wants": Decimal("20.00"),
        "Transportation": Decimal("25.00"),
        "Food": Decimal("35.00"),
    },
    ("both", "own_vehicle", "car"): {
        "Savings": Decimal("15.00"),
        "Wants": Decimal("20.00"),
        "Transportation": Decimal("30.00"),
        "Food": Decimal("35.00"),
    },
    ("both", "walking_biking", None): {
        "Savings": Decimal("30.00"),
        "Wants": Decimal("30.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("35.00"),
    },
    ("both", "none_remote", None): {
        "Savings": Decimal("30.00"),
        "Wants": Decimal("30.00"),
        "Transportation": Decimal("5.00"),
        "Food": Decimal("35.00"),
    },
}

# Minimum required categories in every distribution
REQUIRED_CATEGORIES = {"Savings", "Wants", "Transportation", "Food"}

# Fallback: equal distribution across required categories when lookup key not found
_equal_share = Decimal("100.00") / Decimal(str(len(REQUIRED_CATEGORIES)))
FALLBACK_WEIGHTS: WeightDistribution = {
    category: _equal_share for category in sorted(REQUIRED_CATEGORIES)
}


def get_weights_for_profile(
    employment_status: str,
    commute_method: str,
    vehicle_type: Optional[str] = None,
) -> WeightDistribution:
    """
    Look up the weight distribution for a given lifestyle profile.

    Returns the matching entry from WEIGHT_RULES_TABLE, or an equal
    distribution across the required categories if the key is not found.
    """
    key: ProfileKey = (employment_status, commute_method, vehicle_type)
    return WEIGHT_RULES_TABLE.get(key, FALLBACK_WEIGHTS.copy())
