"""Pydantic schemas for the unified personalized dashboard API endpoints.

Requirements covered: 18.1, 18.2, 18.4
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CategoryBreakdownItem(BaseModel):
    """A single category's spending/income breakdown within a period."""

    category_name: str = Field(..., description="Budget category name")
    total_spent: int = Field(
        ..., description="Total spent in this category (smallest currency unit)"
    )
    total_received: int = Field(
        0, description="Total received in this category (smallest currency unit)"
    )
    budget_limit: Optional[int] = Field(
        None,
        description="Active budget limit for this category (smallest currency unit), if any",
    )
    weight_percentage: Optional[Decimal] = Field(
        None, description="Category weight percentage, if assigned"
    )

    model_config = {"from_attributes": True}


class PeriodSummaryResponse(BaseModel):
    """Response schema for GET /api/dashboard/summary?period={daily|weekly|monthly}.

    Provides period-scoped financial data for the unified dashboard.
    """

    period_type: str = Field(
        ..., description="Period type: 'daily', 'weekly', or 'monthly'"
    )
    total_income: int = Field(
        ..., description="Total income (received) for the period in smallest currency unit"
    )
    total_expenses: int = Field(
        ..., description="Total expenses (spent) for the period in smallest currency unit"
    )
    balance: int = Field(
        ..., description="Net balance (total_income - total_expenses) in smallest currency unit"
    )
    category_breakdown: list[CategoryBreakdownItem] = Field(
        default_factory=list,
        description="Per-category breakdown of spending and budget progress",
    )

    @field_validator("period_type")
    @classmethod
    def validate_period_type(cls, v: str) -> str:
        allowed = ("daily", "weekly", "monthly")
        if v not in allowed:
            raise ValueError(f"period_type must be one of: {', '.join(allowed)}")
        return v

    model_config = {"from_attributes": True}


class PersonalizedInsightResponse(BaseModel):
    """Response schema for GET /api/dashboard/insight.

    Returns a single personalization-aware insight driven by the user's Lifestyle_Profile.
    """

    insight_text: str = Field(
        ..., description="Contextual tip or insight based on user's profile and spending patterns"
    )
    category_focus: Optional[str] = Field(
        None,
        description="The primary category this insight relates to (e.g., 'Savings', 'Transportation')",
    )
