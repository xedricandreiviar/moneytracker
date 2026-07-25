"""API endpoints for AI assistant features.

Provides:
- POST /api/ai/recommend-budget — AI budget recommendation (rate limited)
- POST /api/ai/query — natural language data query (rate limited)
- GET /api/ai/coaching — pending proactive suggestions
- POST /api/ai/coaching/{id}/dismiss — dismiss a suggestion

Requirements covered: 9.5, 9.6, 10.3, 10.5, 11.4, 11.5
"""

import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.ai import (
    AIQueryRequest,
    AIQueryResponse,
    AIRecommendationResponse,
    CoachingDismissResponse,
    CoachingListResponse,
    CoachingSuggestionResponse,
)
from app.services.ai_assistant_service import (
    AIResponse,
    answer_query,
    get_budget_recommendation,
)
from app.services.coaching_service import (
    dismiss_suggestion,
    get_pending_suggestions,
    get_proactive_coaching,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# --- In-memory rate limiter ---

# Stores {user_id: [timestamp1, timestamp2, ...]} for rate tracking
_rate_limit_store: dict[int, list[float]] = defaultdict(list)

# Rate limit configuration: max 10 requests per 60 seconds per user
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60


def _check_rate_limit(user_id: int) -> Optional[JSONResponse]:
    """Check if user has exceeded the rate limit for AI endpoints.

    Uses an in-memory sliding window approach. Returns a JSONResponse
    with 429 status if limit is exceeded, otherwise returns None.

    Args:
        user_id: The user's ID.

    Returns:
        JSONResponse with 429 if rate limited, None otherwise.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Clean old entries outside the window
    _rate_limit_store[user_id] = [
        ts for ts in _rate_limit_store[user_id] if ts > window_start
    ]

    if len(_rate_limit_store[user_id]) >= RATE_LIMIT_MAX_REQUESTS:
        # Calculate estimated wait time
        oldest_in_window = _rate_limit_store[user_id][0]
        retry_after = int(oldest_in_window + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Too many AI requests. "
                    f"Please try again in {retry_after} seconds."
                ),
                "retry_after": retry_after,
            },
        )

    # Record this request
    _rate_limit_store[user_id].append(now)
    return None


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


def _ai_response_to_http(ai_response: AIResponse, timeout_status: int = 503) -> JSONResponse | dict:
    """Convert an AIResponse to the appropriate HTTP response.

    Maps AI error types to HTTP status codes:
    - timeout → 503 Service Unavailable
    - rate_limit → 429 Too Many Requests
    - error → 503 Service Unavailable
    - insufficient_data, out_of_scope → 200 (informational, not HTTP errors)

    Args:
        ai_response: The AIResponse from the service layer.
        timeout_status: HTTP status for timeout errors (default 503).

    Returns:
        JSONResponse with appropriate status code, or dict for 200 responses.
    """
    if ai_response.success:
        return {
            "success": True,
            "message": ai_response.message,
            "error_type": None,
            "data": ai_response.data,
        }

    # Map error types to HTTP status codes
    if ai_response.error_type == "timeout":
        return JSONResponse(
            status_code=timeout_status,
            content={
                "success": False,
                "message": ai_response.message,
                "error_type": ai_response.error_type,
                "data": ai_response.data,
            },
        )
    elif ai_response.error_type == "rate_limit":
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": ai_response.message,
                "error_type": ai_response.error_type,
                "data": ai_response.data,
            },
        )
    elif ai_response.error_type == "error":
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": ai_response.message,
                "error_type": ai_response.error_type,
                "data": ai_response.data,
            },
        )
    else:
        # insufficient_data, out_of_scope — these are valid responses, not HTTP errors
        return {
            "success": False,
            "message": ai_response.message,
            "error_type": ai_response.error_type,
            "data": ai_response.data,
        }


@router.post("/recommend-budget", response_model=AIRecommendationResponse)
def recommend_budget_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Request AI budget recommendation based on spending history.

    Rate limited: max 10 requests per minute per user.
    Returns recommendation with reasoning, or error with guidance.

    Requirement 9.5: Response within 15 seconds (handled by service).
    Requirement 9.6: Handle LLM timeout/error with appropriate messages.
    """
    # Check rate limit
    rate_limit_response = _check_rate_limit(user.id)
    if rate_limit_response is not None:
        return rate_limit_response

    ai_response = get_budget_recommendation(db=db, user_id=user.id)
    return _ai_response_to_http(ai_response, timeout_status=503)


@router.post("/query", response_model=AIQueryResponse)
def query_endpoint(
    request: AIQueryRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Send a natural language question about financial data.

    Rate limited: max 10 requests per minute per user.
    Returns answer with specific numbers and time ranges, or error with guidance.

    Requirement 11.4: Response within 10 seconds (handled by service).
    Requirement 11.5: Timeout message with retry guidance.
    """
    # Check rate limit
    rate_limit_response = _check_rate_limit(user.id)
    if rate_limit_response is not None:
        return rate_limit_response

    ai_response = answer_query(db=db, user_id=user.id, question=request.question)
    return _ai_response_to_http(ai_response, timeout_status=503)


@router.get("/coaching", response_model=CoachingListResponse)
def get_coaching_suggestions_endpoint(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Get pending proactive coaching suggestions.

    Returns all pending suggestions for the current user. Also triggers
    detection of new deviations that may generate fresh suggestions.

    Requirement 10.3: Single-tap accept/dismiss for coaching suggestions.
    """
    # Trigger coaching detection to surface any new suggestions
    get_proactive_coaching(db=db, user_id=user.id)

    # Return all pending suggestions
    pending = get_pending_suggestions(db=db, user_id=user.id)

    suggestions = [
        CoachingSuggestionResponse(
            id=s.id,
            budget_id=s.budget_id,
            suggestion_text=s.suggestion_text,
            deviation_percentage=s.deviation_percentage,
            status=s.status.value if hasattr(s.status, "value") else s.status,
            period_start=s.period_start,
            period_end=s.period_end,
            created_at_utc=s.created_at_utc,
        )
        for s in pending
    ]

    return CoachingListResponse(
        suggestions=suggestions,
        count=len(suggestions),
    )


@router.post("/coaching/{suggestion_id}/dismiss", response_model=CoachingDismissResponse)
def dismiss_coaching_suggestion_endpoint(
    suggestion_id: int,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss a coaching suggestion.

    Returns 404 if the suggestion is not found or not in pending status.

    Requirement 10.5: Dismiss logic prevents re-surfacing unless deviation
    increases by 10+ percentage points.
    """
    result = dismiss_suggestion(db=db, suggestion_id=suggestion_id, user_id=user.id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Coaching suggestion not found or already dismissed.",
        )

    return CoachingDismissResponse(
        id=result.id,
        status=result.status.value if hasattr(result.status, "value") else result.status,
        dismissed_at_utc=result.dismissed_at_utc,
    )
