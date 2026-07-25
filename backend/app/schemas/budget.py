"""Pydantic schemas for budget API endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BudgetCreateRequest(BaseModel):
    """Request schema for POST /api/budgets."""

    period_type: str = Field(
        ..., description="Budget period type: 'weekly' or 'monthly'"
    )
    limit_smallest_unit: int = Field(
        ..., gt=0, description="Positive integer budget limit in smallest currency unit"
    )
    currency_code: str = Field(
        ..., min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    category_id: Optional[int] = Field(
        None, description="Category ID (null for overall budget)"
    )

    @field_validator("period_type")
    @classmethod
    def validate_period_type(cls, v: str) -> str:
        if v not in ("weekly", "monthly"):
            raise ValueError("Period type must be 'weekly' or 'monthly'.")
        return v


class BudgetUpdateRequest(BaseModel):
    """Request schema for PUT /api/budgets/{id}."""

    limit_smallest_unit: int = Field(
        ..., gt=0, description="New positive integer budget limit in smallest currency unit"
    )


class BudgetProjectionResponse(BaseModel):
    """Projection details for a budget period."""

    remaining: int = Field(..., description="Amount remaining in the period")
    projected_spend: int = Field(..., description="Projected total spend for the period")
    status: str = Field(..., description="'on_track' or 'off_track'")
    overage: int = Field(..., description="Projected overage amount (0 if on track)")


class BudgetPeriodResponse(BaseModel):
    """Current period record details."""

    period_start: date
    period_end: date
    spent_smallest_unit: int
    status: str

    model_config = {"from_attributes": True}


class BudgetResponse(BaseModel):
    """Response schema for a single budget."""

    id: int
    user_id: int
    category_id: Optional[int] = None
    period_type: str
    limit_smallest_unit: int
    currency_code: str
    is_active: bool
    created_at_utc: datetime
    current_period: Optional[BudgetPeriodResponse] = None
    projection: Optional[BudgetProjectionResponse] = None

    model_config = {"from_attributes": True}


class BudgetListResponse(BaseModel):
    """Response schema for GET /api/budgets."""

    budgets: list[BudgetResponse]
    count: int
