"""API endpoints for spending insights: weekly/monthly summaries and spike alerts.

Provides:
- GET /api/insights/weekly — current/past weekly summaries
- GET /api/insights/monthly — current/past monthly summaries
- GET /api/insights/spikes — active spending spike alerts

Requirements covered: 5.1, 5.2, 5.6, 6.1, 6.3
"""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.insight import (
    CategoryTotalResponse,
    MonthlySummaryResponse,
    SpendingSpikeResponse,
    SpikesListResponse,
    WeeklySummaryResponse,
)
from app.services.insight_engine import (
    detect_spending_spikes,
    generate_monthly_summary,
    generate_weekly_summary,
)
from app.services.locale_service import LocaleConfig, get_locale_config, get_week_boundaries

router = APIRouter(prefix="/api/insights", tags=["insights"])


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


@router.get("/weekly", response_model=WeeklySummaryResponse)
def get_weekly_summary(
    week_end: Optional[date] = Query(
        default=None,
        description="End date of the week to query. Defaults to current week.",
    ),
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> WeeklySummaryResponse:
    """Get a weekly spending summary.

    If week_end is not provided, returns the summary for the current week.
    The week boundaries are determined by the user's locale (week start day).

    Requirement 5.1: Weekly summary with total spent, received, net, per-category totals.
    """
    locale = _get_user_locale(user)

    if week_end is None:
        # Default to current week
        today = datetime.now(timezone.utc).date()
        _, week_end_date = get_week_boundaries(today, locale)
    else:
        week_end_date = week_end

    summary = generate_weekly_summary(
        db=db,
        user_id=user.id,
        week_end_date=week_end_date,
        locale=locale,
    )

    category_totals = [
        CategoryTotalResponse(
            category_name=ct.category_name,
            total_spent=ct.total_spent,
            total_received=ct.total_received,
            percentage_change=ct.percentage_change,
            is_new=ct.is_new,
        )
        for ct in summary.category_totals
    ]

    return WeeklySummaryResponse(
        user_id=summary.user_id,
        week_start=summary.week_start,
        week_end=summary.week_end,
        total_spent=summary.total_spent,
        total_received=summary.total_received,
        net=summary.net,
        category_totals=category_totals,
        has_prior_period=summary.has_prior_period,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/monthly", response_model=MonthlySummaryResponse)
def get_monthly_summary(
    month: Optional[int] = Query(
        default=None,
        ge=1,
        le=12,
        description="Month number (1-12). Defaults to current month.",
    ),
    year: Optional[int] = Query(
        default=None,
        description="Year. Defaults to current year.",
    ),
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> MonthlySummaryResponse:
    """Get a monthly spending summary.

    If month/year are not provided, returns the summary for the current month.
    Includes absolute and percentage differences vs the prior month.

    Requirement 5.2: Monthly summary with total spent, received, net, category breakdown,
    and comparison to prior month.
    """
    locale = _get_user_locale(user)

    today = datetime.now(timezone.utc).date()
    query_month = month if month is not None else today.month
    query_year = year if year is not None else today.year

    summary = generate_monthly_summary(
        db=db,
        user_id=user.id,
        month=query_month,
        year=query_year,
        locale=locale,
    )

    category_totals = [
        CategoryTotalResponse(
            category_name=ct.category_name,
            total_spent=ct.total_spent,
            total_received=ct.total_received,
            percentage_change=ct.percentage_change,
            is_new=ct.is_new,
        )
        for ct in summary.category_totals
    ]

    return MonthlySummaryResponse(
        user_id=summary.user_id,
        month=summary.month,
        year=summary.year,
        total_spent=summary.total_spent,
        total_received=summary.total_received,
        net=summary.net,
        category_totals=category_totals,
        total_spent_change=summary.total_spent_change,
        total_received_change=summary.total_received_change,
        total_spent_abs_change=summary.total_spent_abs_change,
        total_received_abs_change=summary.total_received_abs_change,
        has_prior_period=summary.has_prior_period,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/spikes", response_model=SpikesListResponse)
def get_spending_spikes(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> SpikesListResponse:
    """Get active spending spike alerts for the current week.

    Detects categories where current week spending exceeds 150% of the
    4-week rolling average.

    Requirement 6.1: Flag category when current week > 150% of rolling 4-week average.
    """
    locale = _get_user_locale(user)

    spikes = detect_spending_spikes(
        db=db,
        user_id=user.id,
        locale=locale,
    )

    spike_responses = [
        SpendingSpikeResponse(
            category_name=spike.category_name,
            current_total=spike.current_total,
            rolling_average=spike.rolling_average,
            threshold_percentage=spike.threshold_percentage,
        )
        for spike in spikes
    ]

    return SpikesListResponse(
        spikes=spike_responses,
        detected_at=datetime.now(timezone.utc),
    )
