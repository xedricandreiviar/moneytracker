"""InsightEngine for generating periodic spending summaries and spike detection.

Provides weekly and monthly summary generation with category breakdowns,
percentage changes vs prior periods, locale-aware formatting, and spending
spike detection with suppression tracking.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.spike_suppression import SpikeSuppression
from app.models.transaction import Transaction, TransactionDirection
from app.services.locale_service import LocaleConfig, format_amount, get_week_boundaries


@dataclass
class CategoryTotal:
    """Spending total for a single category within a period."""

    category_name: str
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    percentage_change: Optional[float] = None  # rounded to 1 decimal, None if no prior
    is_new: bool = False  # True if category had no spending in prior period


@dataclass
class WeeklySummary:
    """Weekly spending summary with category breakdowns."""

    user_id: int
    week_start: date
    week_end: date
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    net: int  # received - spent (smallest currency unit)
    category_totals: list[CategoryTotal] = field(default_factory=list)
    has_prior_period: bool = True


@dataclass
class MonthlySummary:
    """Monthly spending summary with category breakdowns and comparison to prior month."""

    user_id: int
    month: int
    year: int
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    net: int  # received - spent (smallest currency unit)
    category_totals: list[CategoryTotal] = field(default_factory=list)
    total_spent_change: Optional[float] = None  # percentage change vs prior month
    total_received_change: Optional[float] = None  # percentage change vs prior month
    total_spent_abs_change: Optional[int] = None  # absolute change vs prior month
    total_received_abs_change: Optional[int] = None  # absolute change vs prior month
    has_prior_period: bool = True


def _calculate_percentage_change(current: int, previous: int) -> Optional[float]:
    """Calculate percentage change from previous to current value.

    Returns:
        Percentage change rounded to 1 decimal place, or None if previous is zero
        (caller should mark as "new").
    """
    if previous == 0:
        return None  # Caller marks as "new"
    change = ((current - previous) / previous) * 100
    return round(change, 1)


def _get_period_totals_by_category(
    db: Session,
    user_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, dict[str, int]]:
    """Query transaction totals grouped by category for a date range.

    Returns a dict mapping category_name -> {"spent": int, "received": int}.
    Uncategorized transactions are grouped under "Uncategorized".
    """
    results = (
        db.query(
            Category.name,
            Transaction.direction,
            func.sum(Transaction.amount_smallest_unit).label("total"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date_local >= date_from,
            Transaction.transaction_date_local <= date_to,
        )
        .group_by(Category.name, Transaction.direction)
        .all()
    )

    category_totals: dict[str, dict[str, int]] = {}
    for cat_name, direction, total in results:
        name = cat_name if cat_name else "Uncategorized"
        if name not in category_totals:
            category_totals[name] = {"spent": 0, "received": 0}

        if direction == TransactionDirection.spent:
            category_totals[name]["spent"] = total or 0
        else:
            category_totals[name]["received"] = total or 0

    return category_totals


def _get_period_overall_totals(
    db: Session,
    user_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, int]:
    """Query overall spent and received totals for a date range.

    Returns {"spent": int, "received": int}.
    """
    results = (
        db.query(
            Transaction.direction,
            func.sum(Transaction.amount_smallest_unit).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date_local >= date_from,
            Transaction.transaction_date_local <= date_to,
        )
        .group_by(Transaction.direction)
        .all()
    )

    totals = {"spent": 0, "received": 0}
    for direction, total in results:
        if direction == TransactionDirection.spent:
            totals["spent"] = total or 0
        else:
            totals["received"] = total or 0

    return totals


def generate_weekly_summary(
    db: Session,
    user_id: int,
    week_end_date: date,
    locale: LocaleConfig,
) -> WeeklySummary:
    """Generate a weekly spending summary.

    Calculates total spent, received, net, and per-category totals for the week
    ending on week_end_date. Compares with the prior week to calculate percentage
    changes per category.

    Args:
        db: Database session.
        user_id: The user's ID.
        week_end_date: The last day of the week to summarize.
        locale: User's locale config (used for week boundary calculation).

    Returns:
        WeeklySummary with all aggregated data.
    """
    # Calculate current week boundaries
    week_start = week_end_date - timedelta(days=6)

    # Calculate prior week boundaries
    prior_week_end = week_start - timedelta(days=1)
    prior_week_start = prior_week_end - timedelta(days=6)

    # Get current period totals
    current_totals = _get_period_overall_totals(db, user_id, week_start, week_end_date)
    current_categories = _get_period_totals_by_category(db, user_id, week_start, week_end_date)

    # Get prior period totals for comparison
    prior_categories = _get_period_totals_by_category(db, user_id, prior_week_start, prior_week_end)

    # Check if prior period has any data
    prior_totals = _get_period_overall_totals(db, user_id, prior_week_start, prior_week_end)
    has_prior = (prior_totals["spent"] + prior_totals["received"]) > 0 or len(prior_categories) > 0

    # Build category totals with percentage changes
    category_total_list: list[CategoryTotal] = []

    # Include all categories from current period
    all_category_names = set(current_categories.keys())
    # Also include categories that existed in prior but not current (they went to zero)
    all_category_names |= set(prior_categories.keys())

    for cat_name in sorted(all_category_names):
        current_cat = current_categories.get(cat_name, {"spent": 0, "received": 0})
        prior_cat = prior_categories.get(cat_name, {"spent": 0, "received": 0})

        current_spent = current_cat["spent"]
        current_received = current_cat["received"]
        prior_spent = prior_cat["spent"]

        # Calculate percentage change for spent amount
        pct_change = None
        is_new = False

        if has_prior:
            if prior_spent == 0 and current_spent > 0:
                is_new = True
            elif prior_spent > 0:
                pct_change = _calculate_percentage_change(current_spent, prior_spent)

        category_total_list.append(
            CategoryTotal(
                category_name=cat_name,
                total_spent=current_spent,
                total_received=current_received,
                percentage_change=pct_change,
                is_new=is_new,
            )
        )

    total_spent = current_totals["spent"]
    total_received = current_totals["received"]

    return WeeklySummary(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end_date,
        total_spent=total_spent,
        total_received=total_received,
        net=total_received - total_spent,
        category_totals=category_total_list,
        has_prior_period=has_prior,
    )


def _get_month_date_range(month: int, year: int) -> tuple[date, date]:
    """Get the first and last day of a given month.

    Args:
        month: Month number (1-12).
        year: Year.

    Returns:
        Tuple of (first_day, last_day) for the month.
    """
    first_day = date(year, month, 1)
    # Calculate last day by going to next month and subtracting a day
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    return first_day, last_day


def _get_prior_month(month: int, year: int) -> tuple[int, int]:
    """Get the prior month and year.

    Args:
        month: Current month (1-12).
        year: Current year.

    Returns:
        Tuple of (prior_month, prior_year).
    """
    if month == 1:
        return 12, year - 1
    return month - 1, year


def generate_monthly_summary(
    db: Session,
    user_id: int,
    month: int,
    year: int,
    locale: LocaleConfig,
) -> MonthlySummary:
    """Generate a monthly spending summary with comparison to prior month.

    Calculates total spent, received, net, per-category totals, and absolute/percentage
    differences vs the prior month.

    Args:
        db: Database session.
        user_id: The user's ID.
        month: Month number (1-12).
        year: Year.
        locale: User's locale config.

    Returns:
        MonthlySummary with all aggregated and comparison data.
    """
    # Current month date range
    current_start, current_end = _get_month_date_range(month, year)

    # Prior month date range
    prior_month, prior_year = _get_prior_month(month, year)
    prior_start, prior_end = _get_month_date_range(prior_month, prior_year)

    # Get current period totals
    current_totals = _get_period_overall_totals(db, user_id, current_start, current_end)
    current_categories = _get_period_totals_by_category(db, user_id, current_start, current_end)

    # Get prior period totals
    prior_totals = _get_period_overall_totals(db, user_id, prior_start, prior_end)
    prior_categories = _get_period_totals_by_category(db, user_id, prior_start, prior_end)

    # Check if prior period has any data
    has_prior = (prior_totals["spent"] + prior_totals["received"]) > 0 or len(prior_categories) > 0

    # Build category totals with percentage changes
    category_total_list: list[CategoryTotal] = []

    all_category_names = set(current_categories.keys()) | set(prior_categories.keys())

    for cat_name in sorted(all_category_names):
        current_cat = current_categories.get(cat_name, {"spent": 0, "received": 0})
        prior_cat = prior_categories.get(cat_name, {"spent": 0, "received": 0})

        current_spent = current_cat["spent"]
        current_received = current_cat["received"]
        prior_spent = prior_cat["spent"]

        # Calculate percentage change for spent amount
        pct_change = None
        is_new = False

        if has_prior:
            if prior_spent == 0 and current_spent > 0:
                is_new = True
            elif prior_spent > 0:
                pct_change = _calculate_percentage_change(current_spent, prior_spent)

        category_total_list.append(
            CategoryTotal(
                category_name=cat_name,
                total_spent=current_spent,
                total_received=current_received,
                percentage_change=pct_change,
                is_new=is_new,
            )
        )

    total_spent = current_totals["spent"]
    total_received = current_totals["received"]

    # Calculate overall comparison stats
    total_spent_change = None
    total_received_change = None
    total_spent_abs_change = None
    total_received_abs_change = None

    if has_prior:
        total_spent_abs_change = total_spent - prior_totals["spent"]
        total_received_abs_change = total_received - prior_totals["received"]

        if prior_totals["spent"] > 0:
            total_spent_change = _calculate_percentage_change(
                total_spent, prior_totals["spent"]
            )
        if prior_totals["received"] > 0:
            total_received_change = _calculate_percentage_change(
                total_received, prior_totals["received"]
            )

    return MonthlySummary(
        user_id=user_id,
        month=month,
        year=year,
        total_spent=total_spent,
        total_received=total_received,
        net=total_received - total_spent,
        category_totals=category_total_list,
        total_spent_change=total_spent_change,
        total_received_change=total_received_change,
        total_spent_abs_change=total_spent_abs_change,
        total_received_abs_change=total_received_abs_change,
        has_prior_period=has_prior,
    )


# --- Spending Spike Detection ---


@dataclass
class SpendingSpike:
    """Represents a detected spending spike in a category."""

    category_name: str
    current_total: int  # current week spend in smallest currency unit
    rolling_average: float  # 4-week rolling average
    threshold_percentage: int  # always 150


def _get_user_local_today(user_id: int) -> date:
    """Get the current local date for a user.

    In production this would use the user's timezone to determine their local date.
    This function exists as a seam for testing (can be patched).

    Args:
        user_id: The user's ID.

    Returns:
        The user's current local date.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date()


def _is_spike_suppressed(
    db: Session, user_id: int, category_id: int, week_start: date
) -> bool:
    """Check if a spike alert has already been generated for this category/week.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_id: The category ID.
        week_start: The start date of the current week.

    Returns:
        True if a suppression record exists (alert already fired), False otherwise.
    """
    suppression = (
        db.query(SpikeSuppression)
        .filter(
            SpikeSuppression.user_id == user_id,
            SpikeSuppression.category_id == category_id,
            SpikeSuppression.week_start == week_start,
        )
        .first()
    )
    return suppression is not None


def _get_weekly_category_totals(
    db: Session,
    user_id: int,
    category_id: int,
    date_from: date,
    date_to: date,
    locale: LocaleConfig,
) -> list[int]:
    """Get weekly spending totals for a category within a date range.

    Returns a list of weekly totals (one per week that had spending).
    Weeks with no transactions are excluded from the result.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_id: The category ID.
        date_from: Start of the date range (inclusive).
        date_to: End of the date range (inclusive).
        locale: Locale config for determining week boundaries.

    Returns:
        List of weekly spending totals (integers in smallest currency unit).
    """
    # Get all spent transactions for this category in the date range
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.category_id == category_id,
            Transaction.direction == TransactionDirection.spent,
            Transaction.transaction_date_local >= date_from,
            Transaction.transaction_date_local < date_to,
        )
        .all()
    )

    if not transactions:
        return []

    # Group transactions by their week start date
    week_totals: dict[date, int] = {}
    for txn in transactions:
        txn_week_start, _ = get_week_boundaries(txn.transaction_date_local, locale)
        if txn_week_start not in week_totals:
            week_totals[txn_week_start] = 0
        week_totals[txn_week_start] += txn.amount_smallest_unit

    # Return totals sorted by week start date
    return [week_totals[ws] for ws in sorted(week_totals.keys())]


def _get_current_week_category_total(
    db: Session,
    user_id: int,
    category_id: int,
    week_start: date,
    week_end: date,
) -> int:
    """Get total spending for a category in the current week.

    Only counts 'spent' direction transactions.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_id: The category ID.
        week_start: Start of the current week (inclusive).
        week_end: End of the current week (inclusive).

    Returns:
        Total spending in smallest currency unit (0 if no transactions).
    """
    result = (
        db.query(func.sum(Transaction.amount_smallest_unit))
        .filter(
            Transaction.user_id == user_id,
            Transaction.category_id == category_id,
            Transaction.direction == TransactionDirection.spent,
            Transaction.transaction_date_local >= week_start,
            Transaction.transaction_date_local <= week_end,
        )
        .scalar()
    )
    return result or 0


def detect_spending_spikes(
    db: Session,
    user_id: int,
    locale: LocaleConfig,
) -> list[SpendingSpike]:
    """Detect spending spikes across all user categories.

    A spike occurs when current week spending exceeds 150% of the rolling
    4-week average for a category.

    Algorithm:
    1. For each user category, check if spike already suppressed this week
    2. Get 4-week rolling weekly totals for the category
    3. Skip if fewer than 4 weeks of data
    4. Calculate rolling average, compare current week total
    5. If current > 150% of average, flag as spike and create SpikeSuppression record

    Requirements:
    - 6.1: Flag category when current week > 150% of rolling 4-week average
    - 6.2: Do not evaluate categories with fewer than 4 weeks of history
    - 6.5: At most one spike alert per category per calendar week

    Args:
        db: Database session.
        user_id: The user's ID.
        locale: User's locale config (used for week boundary calculation).

    Returns:
        List of SpendingSpike objects for categories with detected spikes.
    """
    today = _get_user_local_today(user_id)
    week_start, week_end = get_week_boundaries(today, locale)
    spikes: list[SpendingSpike] = []

    # Get all categories for the user
    categories = db.query(Category).filter(Category.user_id == user_id).all()

    for category in categories:
        # Step 1: Check if already alerted this category this week
        if _is_spike_suppressed(db, user_id, category.id, week_start):
            continue

        # Step 2: Get 4-week rolling history (the 4 weeks before the current week)
        four_weeks_ago = week_start - timedelta(weeks=4)
        weekly_totals = _get_weekly_category_totals(
            db, user_id, category.id, four_weeks_ago, week_start, locale
        )

        # Step 3: Skip if fewer than 4 weeks of data
        if len(weekly_totals) < 4:
            continue

        # Step 4: Calculate rolling average and compare
        rolling_average = sum(weekly_totals) / len(weekly_totals)

        current_week_total = _get_current_week_category_total(
            db, user_id, category.id, week_start, week_end
        )

        # Step 5: Flag as spike if current > 150% of average
        # Guard against zero average (shouldn't happen with 4 weeks of data, but safe)
        if rolling_average > 0 and current_week_total > (rolling_average * 1.5):
            spikes.append(
                SpendingSpike(
                    category_name=category.name,
                    current_total=current_week_total,
                    rolling_average=rolling_average,
                    threshold_percentage=150,
                )
            )
            # Create suppression record to prevent duplicate alerts this week
            suppression = SpikeSuppression(
                user_id=user_id,
                category_id=category.id,
                week_start=week_start,
                week_end=week_end,
            )
            db.add(suppression)
            db.commit()

    return spikes
