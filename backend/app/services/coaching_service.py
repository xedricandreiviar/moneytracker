"""AI Proactive Coaching Service.

Detects budget deviations at the midpoint of a budget period and generates
per-budget coaching suggestions with reasoning. Implements dismiss logic
that prevents re-surfacing unless deviation increases by 10+ percentage points.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus
from app.models.coaching_suggestion import CoachingSuggestion, CoachingSuggestionStatus

logger = logging.getLogger(__name__)


@dataclass
class DeviationInfo:
    """Details about a budget's deviation from pro-rated expected spend."""

    budget_id: int
    actual_spent: int
    pro_rated_expected: int
    deviation_amount: int
    deviation_percentage: float
    period_start: date
    period_end: date
    days_elapsed: int
    total_days: int


@dataclass
class CoachingSuggestionResult:
    """Result of generating a coaching suggestion."""

    suggestion: CoachingSuggestion
    deviation_info: DeviationInfo


def _calculate_deviation(
    budget: Budget,
    period: BudgetPeriodRecord,
    today: Optional[date] = None,
) -> Optional[DeviationInfo]:
    """Calculate the deviation of actual spending from pro-rated budget amount.

    Pro-rated amount = (budget_limit / total_days) * days_elapsed
    Only returns a result if we're at or past the midpoint of the period.

    Args:
        budget: The Budget instance.
        period: The active BudgetPeriodRecord.
        today: Override for current date (defaults to date.today()).

    Returns:
        DeviationInfo if at midpoint and deviation > 20%, else None.
    """
    if today is None:
        today = date.today()

    total_days = (period.period_end - period.period_start).days + 1
    days_elapsed = (today - period.period_start).days + 1

    # Only check at midpoint: days_elapsed >= total_days / 2
    midpoint = total_days / 2
    if days_elapsed < midpoint:
        return None

    # Calculate pro-rated expected spend
    pro_rated_expected = int((budget.limit_smallest_unit / total_days) * days_elapsed)

    if pro_rated_expected == 0:
        return None

    actual_spent = period.spent_smallest_unit
    deviation_amount = actual_spent - pro_rated_expected
    deviation_percentage = abs(deviation_amount) / pro_rated_expected * 100

    # Only flag if deviation is > 20%
    if deviation_percentage <= 20.0:
        return None

    return DeviationInfo(
        budget_id=budget.id,
        actual_spent=actual_spent,
        pro_rated_expected=pro_rated_expected,
        deviation_amount=deviation_amount,
        deviation_percentage=deviation_percentage,
        period_start=period.period_start,
        period_end=period.period_end,
        days_elapsed=days_elapsed,
        total_days=total_days,
    )


def _should_resurface(
    dismissed_suggestion: CoachingSuggestion,
    current_deviation_percentage: float,
) -> bool:
    """Determine if a dismissed suggestion should be re-surfaced.

    A dismissed suggestion is re-surfaced only if the current deviation
    exceeds the dismissed deviation by 10+ percentage points.

    Args:
        dismissed_suggestion: The previously dismissed CoachingSuggestion.
        current_deviation_percentage: The current deviation percentage.

    Returns:
        True if the suggestion should be re-surfaced, False otherwise.
    """
    return current_deviation_percentage >= dismissed_suggestion.deviation_percentage + 10.0


def _get_existing_suggestion_for_period(
    db: Session,
    budget_id: int,
    period_start: date,
    period_end: date,
) -> Optional[CoachingSuggestion]:
    """Get the most recent suggestion for a budget in a specific period.

    Args:
        db: Database session.
        budget_id: The budget's ID.
        period_start: The period start date.
        period_end: The period end date.

    Returns:
        The most recent CoachingSuggestion for this budget/period, or None.
    """
    return (
        db.query(CoachingSuggestion)
        .filter(
            CoachingSuggestion.budget_id == budget_id,
            CoachingSuggestion.period_start == period_start,
            CoachingSuggestion.period_end == period_end,
        )
        .order_by(CoachingSuggestion.created_at_utc.desc())
        .first()
    )


def _generate_suggestion_text(
    deviation_info: DeviationInfo,
    budget: Budget,
) -> str:
    """Generate the suggestion text with reasoning.

    Includes the deviation amount, pro-rated expected spend, and
    contextual information about the budget period.

    Args:
        deviation_info: The calculated deviation details.
        budget: The Budget instance.

    Returns:
        A plain-language suggestion string.
    """
    direction = "over" if deviation_info.deviation_amount > 0 else "under"
    abs_deviation = abs(deviation_info.deviation_amount)

    suggestion = (
        f"Your spending is {direction} budget by {abs_deviation} "
        f"(smallest currency unit). "
        f"At day {deviation_info.days_elapsed} of {deviation_info.total_days}, "
        f"the pro-rated expected spend is {deviation_info.pro_rated_expected}, "
        f"but actual spend is {deviation_info.actual_spent}. "
        f"That's a {deviation_info.deviation_percentage:.1f}% deviation. "
    )

    if deviation_info.deviation_amount > 0:
        suggestion += (
            "Consider reducing spending for the remainder of this period "
            "or adjusting your budget limit upward if this level is sustainable."
        )
    else:
        suggestion += (
            "You're well under budget. Consider if this budget is overly generous "
            "and could be reduced, or continue saving the surplus."
        )

    return suggestion


def get_proactive_coaching(
    db: Session,
    user_id: int,
    today: Optional[date] = None,
) -> list[CoachingSuggestionResult]:
    """Detect budget deviations and generate proactive coaching suggestions.

    For each active budget at or past its period midpoint:
    1. Calculate deviation from pro-rated expected spend
    2. If deviation > 20%, check if a suggestion already exists
    3. If no existing suggestion, create a new one
    4. If existing suggestion is dismissed, only re-surface if deviation
       increased by 10+ percentage points
    5. If existing suggestion is pending, skip (already active)

    Args:
        db: Database session.
        user_id: The user's ID.
        today: Override for current date (defaults to date.today()).

    Returns:
        List of CoachingSuggestionResult for newly created or re-surfaced suggestions.
    """
    if today is None:
        today = date.today()

    # Get all active budgets for the user
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user_id, Budget.is_active == True)
        .all()
    )

    results: list[CoachingSuggestionResult] = []

    for budget in budgets:
        # Get the active period record
        period = (
            db.query(BudgetPeriodRecord)
            .filter(
                BudgetPeriodRecord.budget_id == budget.id,
                BudgetPeriodRecord.status == BudgetPeriodStatus.active,
            )
            .order_by(BudgetPeriodRecord.period_start.desc())
            .first()
        )

        if period is None:
            continue

        # Calculate deviation
        deviation_info = _calculate_deviation(budget, period, today)
        if deviation_info is None:
            continue

        # Check for existing suggestion in this period
        existing = _get_existing_suggestion_for_period(
            db, budget.id, period.period_start, period.period_end
        )

        if existing is not None:
            if existing.status == CoachingSuggestionStatus.pending:
                # Already have a pending suggestion, skip
                continue
            elif existing.status == CoachingSuggestionStatus.accepted:
                # User accepted, don't re-surface
                continue
            elif existing.status == CoachingSuggestionStatus.dismissed:
                # Only re-surface if deviation increased by 10+ percentage points
                if not _should_resurface(existing, deviation_info.deviation_percentage):
                    continue

        # Generate and store a new suggestion
        suggestion_text = _generate_suggestion_text(deviation_info, budget)

        suggestion = CoachingSuggestion(
            user_id=user_id,
            budget_id=budget.id,
            suggestion_text=suggestion_text,
            deviation_percentage=deviation_info.deviation_percentage,
            status=CoachingSuggestionStatus.pending,
            period_start=period.period_start,
            period_end=period.period_end,
        )
        db.add(suggestion)
        results.append(CoachingSuggestionResult(
            suggestion=suggestion,
            deviation_info=deviation_info,
        ))

    if results:
        db.commit()
        for result in results:
            db.refresh(result.suggestion)

    return results


def dismiss_suggestion(
    db: Session,
    suggestion_id: int,
    user_id: int,
) -> Optional[CoachingSuggestion]:
    """Dismiss a coaching suggestion.

    Sets the status to 'dismissed' and records the dismissal timestamp.

    Args:
        db: Database session.
        suggestion_id: The suggestion's ID.
        user_id: The user's ID (for ownership check).

    Returns:
        The dismissed CoachingSuggestion, or None if not found.
    """
    suggestion = (
        db.query(CoachingSuggestion)
        .filter(
            CoachingSuggestion.id == suggestion_id,
            CoachingSuggestion.user_id == user_id,
            CoachingSuggestion.status == CoachingSuggestionStatus.pending,
        )
        .first()
    )

    if suggestion is None:
        return None

    suggestion.status = CoachingSuggestionStatus.dismissed
    suggestion.dismissed_at_utc = datetime.utcnow()
    db.commit()
    db.refresh(suggestion)
    return suggestion


def accept_suggestion(
    db: Session,
    suggestion_id: int,
    user_id: int,
) -> Optional[CoachingSuggestion]:
    """Accept a coaching suggestion.

    Sets the status to 'accepted'.

    Args:
        db: Database session.
        suggestion_id: The suggestion's ID.
        user_id: The user's ID (for ownership check).

    Returns:
        The accepted CoachingSuggestion, or None if not found.
    """
    suggestion = (
        db.query(CoachingSuggestion)
        .filter(
            CoachingSuggestion.id == suggestion_id,
            CoachingSuggestion.user_id == user_id,
            CoachingSuggestion.status == CoachingSuggestionStatus.pending,
        )
        .first()
    )

    if suggestion is None:
        return None

    suggestion.status = CoachingSuggestionStatus.accepted
    db.commit()
    db.refresh(suggestion)
    return suggestion


def get_pending_suggestions(
    db: Session,
    user_id: int,
) -> list[CoachingSuggestion]:
    """Get all pending coaching suggestions for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        List of pending CoachingSuggestion instances.
    """
    return (
        db.query(CoachingSuggestion)
        .filter(
            CoachingSuggestion.user_id == user_id,
            CoachingSuggestion.status == CoachingSuggestionStatus.pending,
        )
        .order_by(CoachingSuggestion.created_at_utc.desc())
        .all()
    )
