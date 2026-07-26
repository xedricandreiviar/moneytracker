"""Pydantic schemas for category weight API endpoints.

Requirements covered: 16.1, 16.5, 16.6, 16.7
"""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class CategoryWeightResponse(BaseModel):
    """Response schema for a single category weight entry."""

    category_name: str = Field(..., description="Budget category name")
    weight_percentage: Decimal = Field(
        ..., description="Percentage allocation (e.g., 25.00 for 25%)"
    )
    is_manual_override: bool = Field(
        False,
        description="True if manually set by user, False if derived from Weight_Rules_Table",
    )

    model_config = {"from_attributes": True}


class CategoryWeightOverrideRequest(BaseModel):
    """Request schema for PUT /api/weights/{category_name}.

    Allows the user to manually override a single category's weight percentage.
    The system will redistribute remaining categories proportionally to maintain 100% total.
    """

    category_name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the category to override"
    )
    new_percentage: Decimal = Field(
        ..., description="New weight percentage (exclusive range: 0 < value < 100)"
    )

    @field_validator("new_percentage")
    @classmethod
    def validate_percentage_range(cls, v: Decimal) -> Decimal:
        """Weight percentage must be between 0 and 100 exclusive."""
        if v <= Decimal("0") or v >= Decimal("100"):
            raise ValueError(
                "new_percentage must be greater than 0 and less than 100"
            )
        return v


class WeightListResponse(BaseModel):
    """Response schema for GET /api/weights."""

    weights: list[CategoryWeightResponse] = Field(
        ..., description="All category weight entries for the user"
    )
    total_percentage: Decimal = Field(
        ..., description="Sum of all weight percentages (should always be 100.00)"
    )
