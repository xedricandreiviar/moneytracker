"""Pydantic schemas for insight API endpoints (weekly/monthly summaries and spike alerts).

Requirements covered: 5.1, 5.2, 5.6, 6.1, 6.3
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class CategoryTotalResponse(BaseModel):
    """Single category total within a periodic summary."""

    category_name: str
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    percentage_change: Optional[float] = None  # rounded to 1 decimal, None if no prior
    is_new: bool = False  # True if category had no spending in prior period

    model_config = {"from_attributes": True}


class WeeklySummaryResponse(BaseModel):
    """Response schema for a weekly spending summary."""

    user_id: int
    week_start: date
    week_end: date
    total_spent: int
    total_received: int
    net: int  # received - spent
    category_totals: list[CategoryTotalResponse] = []
    has_prior_period: bool = True
    generated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MonthlySummaryResponse(BaseModel):
    """Response schema for a monthly spending summary."""

    user_id: int
    month: int
    year: int
    total_spent: int
    total_received: int
    net: int  # received - spent
    category_totals: list[CategoryTotalResponse] = []
    total_spent_change: Optional[float] = None
    total_received_change: Optional[float] = None
    total_spent_abs_change: Optional[int] = None
    total_received_abs_change: Optional[int] = None
    has_prior_period: bool = True
    generated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SpendingSpikeResponse(BaseModel):
    """Response schema for a detected spending spike."""

    category_name: str
    current_total: int  # current week spend in smallest currency unit
    rolling_average: float  # 4-week rolling average
    threshold_percentage: int  # always 150

    model_config = {"from_attributes": True}


class SpikesListResponse(BaseModel):
    """Response schema for list of active spending spike alerts."""

    spikes: list[SpendingSpikeResponse] = []
    detected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
