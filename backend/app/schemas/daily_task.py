"""Pydantic schemas for daily task and streak API endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DailyTaskResponse(BaseModel):
    """Response schema for the current daily task."""

    id: int
    user_id: int
    task_date: date
    status: str
    completion_type: Optional[str] = None
    completed_at_utc: Optional[datetime] = None
    hours_remaining: float

    model_config = {"from_attributes": True}


class DailyTaskCompleteResponse(BaseModel):
    """Response schema for completing a daily task."""

    id: int
    user_id: int
    task_date: date
    status: str
    completion_type: str
    completed_at_utc: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GracePeriodResponse(BaseModel):
    """Response schema for grace period status."""

    is_active: bool
    task_id: Optional[int] = None
    task_date: Optional[date] = None
    remaining_hours: float = 0.0
    remaining_minutes: float = 0.0


class StreakResponse(BaseModel):
    """Response schema for current streak info."""

    current_streak: int
    grace_period_active: bool
    grace_remaining_hours: float = 0.0
    grace_remaining_minutes: float = 0.0
