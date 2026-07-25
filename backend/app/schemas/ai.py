"""Pydantic request/response schemas for AI API endpoints.

Provides schemas for:
- POST /api/ai/recommend-budget
- POST /api/ai/query
- GET /api/ai/coaching
- POST /api/ai/coaching/{id}/dismiss
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Request schemas ---


class AIQueryRequest(BaseModel):
    """Request body for natural language data query."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language question about financial data.",
    )


# --- Response schemas ---


class AIRecommendationResponse(BaseModel):
    """Response for budget recommendation endpoint."""

    success: bool
    message: str
    error_type: Optional[str] = None
    data: Optional[dict] = None


class AIQueryResponse(BaseModel):
    """Response for natural language query endpoint."""

    success: bool
    message: str
    error_type: Optional[str] = None
    data: Optional[dict] = None


class CoachingSuggestionResponse(BaseModel):
    """Single coaching suggestion in response."""

    id: int
    budget_id: int
    suggestion_text: str
    deviation_percentage: float
    status: str
    period_start: date
    period_end: date
    created_at_utc: datetime

    model_config = ConfigDict(from_attributes=True)


class CoachingListResponse(BaseModel):
    """Response for pending coaching suggestions list."""

    suggestions: list[CoachingSuggestionResponse]
    count: int


class CoachingDismissResponse(BaseModel):
    """Response for dismissing a coaching suggestion."""

    id: int
    status: str
    dismissed_at_utc: Optional[datetime] = None
