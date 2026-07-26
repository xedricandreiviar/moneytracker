"""API endpoints for the unified personalized dashboard.

Provides:
- GET /api/dashboard/summary?period={daily|weekly|monthly} — period-scoped financial summary
- GET /api/dashboard/insight — personalized insight based on user profile and weights

Requirements covered: 18.1, 18.2, 18.3, 18.4
"""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import (
    CategoryBreakdownItem,
    PeriodSummaryResponse,
    PersonalizedInsightResponse,
)
from app.services.category_weight_service import get_weights
from app.services.insight_engine import get_period_summary
from app.services.locale_service import LocaleConfig, get_locale_config

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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


def _get_user_locale(user: User) -> LocaleConfig:
    """Resolve user's locale configuration.

    Falls back to US locale if user has no locale configured.
    """
    if user.locale and user.locale.country_code:
        return get_locale_config(user.locale.country_code)
    return get_locale_config("US")


def _get_personalized_insight(
    db: Session,
    user: User,
    weights,
) -> PersonalizedInsightResponse:
    """Generate a personalized insight based on user profile and category weights.

    Selects a contextual tip based on the highest-weight category and
    current spending patterns.

    Args:
        db: Database session.
        user: The current user.
        weights: List of CategoryWeight entries for the user.

    Returns:
        PersonalizedInsightResponse with insight text and category focus.
    """
    # Try to use the InsightEngine's get_personalized_insight if available
    try:
        from app.services.insight_engine import get_personalized_insight

        insight_text = get_personalized_insight(
            db=db,
            user_id=user.id,
            profile={
                "employment_status": user.employment_status.value if user.employment_status else None,
                "commute_method": user.commute_method.value if user.commute_method else None,
                "vehicle_type": user.vehicle_type.value if user.vehicle_type else None,
            },
            weights=weights,
        )
        # Determine category focus from highest weight
        category_focus = None
        if weights:
            highest = max(weights, key=lambda w: w.weight_percentage)
            category_focus = highest.category_name
        return PersonalizedInsightResponse(
            insight_text=insight_text,
            category_focus=category_focus,
        )
    except (ImportError, AttributeError):
        pass

    # Fallback: generate insight locally based on highest-weight category
    if not weights:
        return PersonalizedInsightResponse(
            insight_text="Complete your profile to get personalized insights.",
            category_focus=None,
        )

    # Find highest-weight category
    highest_weight = max(weights, key=lambda w: w.weight_percentage)
    category_focus = highest_weight.category_name

    # Generate contextual tip based on the category
    insight_text = _generate_tip_for_category(category_focus, highest_weight.weight_percentage)

    return PersonalizedInsightResponse(
        insight_text=insight_text,
        category_focus=category_focus,
    )


def _generate_tip_for_category(category_name: str, weight_percentage) -> str:
    """Generate a contextual tip based on the highest-weight category.

    Args:
        category_name: The category with highest weight allocation.
        weight_percentage: The weight percentage for context.

    Returns:
        A personalized tip string.
    """
    tips = {
        "Savings": (
            f"Savings is your top priority at {weight_percentage}%. "
            "Consider automating transfers to stay on track with your savings goals."
        ),
        "Transportation": (
            f"Transportation takes {weight_percentage}% of your budget. "
            "Track fuel and commute costs closely to spot savings opportunities."
        ),
        "Food": (
            f"Food accounts for {weight_percentage}% of your budget. "
            "Meal planning can help reduce impulse spending in this category."
        ),
        "Wants": (
            f"Wants allocation is {weight_percentage}%. "
            "Set a weekly spending cap to enjoy discretionary purchases without overspending."
        ),
    }

    return tips.get(
        category_name,
        f"{category_name} is your highest-weighted category at {weight_percentage}%. "
        "Keep an eye on spending here to stay within your budget goals.",
    )


@router.get("/summary", response_model=PeriodSummaryResponse)
def get_dashboard_summary(
    period: str = Query(
        ...,
        description="Period type: 'daily', 'weekly', or 'monthly'",
        pattern="^(daily|weekly|monthly)$",
    ),
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> PeriodSummaryResponse | JSONResponse:
    """Get period-scoped dashboard summary data.

    Returns total income, total expenses, balance, and per-category breakdown
    for the selected period (daily, weekly, or monthly) relative to today.

    Requirements: 18.1, 18.2, 18.3
    """
    if not user.profile_completed:
        return JSONResponse(
            status_code=400,
            content={"detail": "Profile not completed. Dashboard requires a completed profile."},
        )

    locale = _get_user_locale(user)
    today = datetime.now(timezone.utc).date()

    summary = get_period_summary(
        db=db,
        user_id=user.id,
        period_type=period,
        reference_date=today,
        locale=locale,
    )

    # Enrich category breakdown with budget limits and weight percentages
    weights = get_weights(db=db, user_id=user.id)
    weight_map = {w.category_name: w.weight_percentage for w in weights}

    # Build budget limit map from active budgets
    from app.models.budget import Budget

    active_budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.is_active == True)
        .all()
    )
    budget_limit_map: dict[str, int] = {}
    for budget in active_budgets:
        if budget.category and budget.category.name:
            budget_limit_map[budget.category.name] = budget.limit_smallest_unit
        elif budget.category_id is None:
            # Overall budget — could map to "Overall" but skip for per-category breakdown
            pass

    category_breakdown = [
        CategoryBreakdownItem(
            category_name=item["category_name"],
            total_spent=item["total_spent"],
            total_received=item.get("total_received", 0),
            budget_limit=budget_limit_map.get(item["category_name"]),
            weight_percentage=weight_map.get(item["category_name"]),
        )
        for item in summary.category_breakdown
    ]

    return PeriodSummaryResponse(
        period_type=summary.period_type,
        total_income=summary.total_income,
        total_expenses=summary.total_expenses,
        balance=summary.balance,
        category_breakdown=category_breakdown,
    )


@router.get("/insight", response_model=PersonalizedInsightResponse)
def get_dashboard_insight(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> PersonalizedInsightResponse | JSONResponse:
    """Get a personalized insight for the dashboard.

    Returns a contextual tip based on the user's highest-weight category
    and current spending patterns, driven by the Lifestyle_Profile.

    Requirements: 18.4
    """
    if not user.profile_completed:
        return JSONResponse(
            status_code=400,
            content={"detail": "Profile not completed. Insights require a completed profile."},
        )

    weights = get_weights(db=db, user_id=user.id)

    return _get_personalized_insight(db=db, user=user, weights=weights)
