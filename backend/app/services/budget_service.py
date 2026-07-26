"""BudgetService for creating, managing, and projecting budgets.

Handles budget creation with validation, uniqueness enforcement,
period record tracking, auto-rollover, projection calculations,
budget threshold notifications, and dynamic budget recalculation on income.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.budget import (
    Budget,
    BudgetPeriodRecord,
    BudgetPeriodStatus,
    BudgetPeriodType,
)
from app.models.budget_limit_change_log import BudgetLimitChangeLog
from app.models.category import Category
from app.models.category_weight import CategoryWeight
from app.models.notification import Notification
from app.models.transaction import Transaction, TransactionDirection
from app.services.locale_service import LocaleConfig, get_week_boundaries

logger = logging.getLogger(__name__)


class BudgetValidationError(Exception):
    """Raised when budget input fails validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class BudgetConflictError(Exception):
    """Raised when a duplicate budget already exists for the same scope/period."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class BudgetProjection:
    """Result of budget projection calculation."""

    remaining: int
    projected_spend: int
    status: str  # "on_track" or "off_track"
    overage: int


def _validate_budget_limit(
    limit_smallest_unit: int,
    currency_code: str,
    decimal_precision: int,
) -> None:
    """Validate the budget limit value.

    Args:
        limit_smallest_unit: Must be a positive integer.
        currency_code: ISO 4217 currency code.
        decimal_precision: The decimal precision for the currency.

    Raises:
        BudgetValidationError: If limit is invalid.
    """
    if not isinstance(limit_smallest_unit, int):
        raise BudgetValidationError(
            "limit", "Spending limit must be a numeric value."
        )

    if limit_smallest_unit <= 0:
        raise BudgetValidationError(
            "limit", "Spending limit must be a positive value."
        )

    # Validate precision: for currencies with decimal_precision > 0,
    # the smallest unit represents the fractional component.
    # Any positive integer is valid for the smallest unit representation.
    # The precision check ensures the limit maps to a valid display value.
    if decimal_precision > 0:
        # Check the limit can represent a valid amount
        # (no additional constraint needed for integers in smallest unit)
        pass


def _check_budget_uniqueness(
    db: Session,
    user_id: int,
    category_id: Optional[int],
    period_type: BudgetPeriodType,
    exclude_budget_id: Optional[int] = None,
) -> None:
    """Check that no active budget exists for the same category/scope and period.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_id: Category ID (None for overall budget).
        period_type: The budget period type.
        exclude_budget_id: Optional budget ID to exclude (for updates).

    Raises:
        BudgetConflictError: If a duplicate active budget exists.
    """
    query = db.query(Budget).filter(
        Budget.user_id == user_id,
        Budget.period_type == period_type,
        Budget.is_active == True,
    )

    if category_id is None:
        query = query.filter(Budget.category_id.is_(None))
    else:
        query = query.filter(Budget.category_id == category_id)

    if exclude_budget_id is not None:
        query = query.filter(Budget.id != exclude_budget_id)

    existing = query.first()
    if existing:
        scope = "overall" if category_id is None else f"category (id={category_id})"
        raise BudgetConflictError(
            f"An active {period_type.value} budget already exists for {scope}."
        )


def _compute_period_boundaries(
    period_type: BudgetPeriodType,
    reference_date: date,
    locale: LocaleConfig,
) -> tuple[date, date]:
    """Compute the start and end dates for a budget period containing the reference date.

    Args:
        period_type: Weekly or monthly.
        reference_date: The date to compute boundaries for.
        locale: Locale config (needed for week start day).

    Returns:
        Tuple of (period_start, period_end).
    """
    if period_type == BudgetPeriodType.weekly:
        return get_week_boundaries(reference_date, locale)
    else:
        # Monthly: first day to last day of the month
        period_start = reference_date.replace(day=1)
        # Find last day of month
        if reference_date.month == 12:
            next_month_start = reference_date.replace(year=reference_date.year + 1, month=1, day=1)
        else:
            next_month_start = reference_date.replace(month=reference_date.month + 1, day=1)
        period_end = next_month_start - timedelta(days=1)
        return (period_start, period_end)


def create_budget(
    db: Session,
    user_id: int,
    period_type: str,
    limit_smallest_unit: int,
    currency_code: str,
    decimal_precision: int = 2,
    category_id: Optional[int] = None,
    locale: Optional[LocaleConfig] = None,
    reference_date: Optional[date] = None,
) -> Budget:
    """Create a new budget with validation and uniqueness enforcement.

    Args:
        db: Database session.
        user_id: The user's ID.
        period_type: "weekly" or "monthly".
        limit_smallest_unit: Positive integer budget limit in smallest currency unit.
        currency_code: ISO 4217 currency code.
        decimal_precision: Decimal precision for the currency (default 2).
        category_id: Optional category ID (None for overall budget).
        locale: Optional locale config for period boundary calculation.
        reference_date: Optional date to compute the initial period (defaults to today).

    Returns:
        The created Budget instance with its initial BudgetPeriodRecord.

    Raises:
        BudgetValidationError: If the limit is invalid.
        BudgetConflictError: If a duplicate active budget exists.
    """
    # Validate period type
    try:
        budget_period_type = BudgetPeriodType(period_type)
    except ValueError:
        raise BudgetValidationError(
            "period_type", "Period type must be 'weekly' or 'monthly'."
        )

    # Validate limit
    _validate_budget_limit(limit_smallest_unit, currency_code, decimal_precision)

    # Check uniqueness
    _check_budget_uniqueness(db, user_id, category_id, budget_period_type)

    # Create budget
    budget = Budget(
        user_id=user_id,
        category_id=category_id,
        period_type=budget_period_type,
        limit_smallest_unit=limit_smallest_unit,
        currency_code=currency_code.upper(),
        is_active=True,
    )
    db.add(budget)
    db.flush()

    # Create the initial period record
    if reference_date is None:
        reference_date = date.today()

    if locale is None:
        # Default locale for period calculation
        from app.services.locale_service import LOCALE_CONFIGS
        locale = LOCALE_CONFIGS.get("US")

    period_start, period_end = _compute_period_boundaries(
        budget_period_type, reference_date, locale
    )

    period_record = BudgetPeriodRecord(
        budget_id=budget.id,
        period_start=period_start,
        period_end=period_end,
        spent_smallest_unit=0,
        status=BudgetPeriodStatus.active,
    )
    db.add(period_record)
    db.commit()
    db.refresh(budget)

    return budget


def get_active_period_record(
    db: Session,
    budget_id: int,
) -> Optional[BudgetPeriodRecord]:
    """Get the current active period record for a budget.

    Args:
        db: Database session.
        budget_id: The budget's ID.

    Returns:
        The active BudgetPeriodRecord, or None if no active period exists.
    """
    return (
        db.query(BudgetPeriodRecord)
        .filter(
            BudgetPeriodRecord.budget_id == budget_id,
            BudgetPeriodRecord.status == BudgetPeriodStatus.active,
        )
        .order_by(BudgetPeriodRecord.period_start.desc())
        .first()
    )


def update_spent(
    db: Session,
    budget_id: int,
    amount_smallest_unit: int,
) -> Optional[BudgetPeriodRecord]:
    """Update the spent amount on the active period record for a budget.

    Called when a transaction is logged that applies to this budget.

    Args:
        db: Database session.
        budget_id: The budget's ID.
        amount_smallest_unit: The transaction amount to add to spent.

    Returns:
        The updated BudgetPeriodRecord, or None if no active period exists.
    """
    period_record = get_active_period_record(db, budget_id)
    if period_record is None:
        return None

    period_record.spent_smallest_unit += amount_smallest_unit

    # Update status if exceeded
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if budget and period_record.spent_smallest_unit > budget.limit_smallest_unit:
        period_record.status = BudgetPeriodStatus.exceeded

    db.commit()
    db.refresh(period_record)

    # Check budget thresholds and fire notifications if needed
    if budget:
        check_budget_thresholds(db, budget_id)

    return period_record


def check_budget_thresholds(
    db: Session,
    budget_id: int,
) -> list[Notification]:
    """Check if budget thresholds (80%, 100%) have been crossed and fire notifications.

    Uses idempotency keys (budget_id + period_start + threshold) to ensure each
    threshold notification fires exactly once per budget period.

    Args:
        db: Database session.
        budget_id: The budget's ID.

    Returns:
        List of newly created Notification records (may be empty).
    """
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if budget is None:
        return []

    period_record = get_active_period_record(db, budget_id)
    if period_record is None:
        return []

    notifications_created = []
    spent = period_record.spent_smallest_unit
    limit = budget.limit_smallest_unit

    # Define thresholds to check
    thresholds = []
    if spent >= limit * 0.8:
        thresholds.append(("budget_80", 80))
    if spent >= limit:
        thresholds.append(("budget_100", 100))

    for notification_type, threshold_pct in thresholds:
        # Build idempotency key: budget_id + period_start + threshold
        idempotency_key = (
            f"{budget_id}_{period_record.period_start.isoformat()}_{threshold_pct}"
        )

        # Check if notification already exists for this key
        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == budget.user_id,
                Notification.notification_type == notification_type,
                Notification.payload_json.contains(idempotency_key),
            )
            .first()
        )

        if existing is None:
            # Create the notification
            if threshold_pct == 80:
                title = "Budget approaching limit"
                body = (
                    f"You've spent 80% of your budget "
                    f"(period starting {period_record.period_start.isoformat()})."
                )
            else:
                title = "Budget exceeded"
                body = (
                    f"You've exceeded 100% of your budget "
                    f"(period starting {period_record.period_start.isoformat()})."
                )

            notification = Notification(
                user_id=budget.user_id,
                notification_type=notification_type,
                title=title,
                body=body,
                payload_json=f'{{"idempotency_key": "{idempotency_key}", "budget_id": {budget_id}}}',
                is_read=False,
            )
            db.add(notification)
            notifications_created.append(notification)

    if notifications_created:
        db.commit()
        for n in notifications_created:
            db.refresh(n)

    return notifications_created


def rollover_period(
    db: Session,
    budget_id: int,
    locale: Optional[LocaleConfig] = None,
) -> Optional[BudgetPeriodRecord]:
    """Create a new period record for a budget whose current period has ended.

    Auto-rollover: creates a new period with the same limit when the current
    period ends. Marks the old period as completed.

    Args:
        db: Database session.
        budget_id: The budget's ID.
        locale: Optional locale config for week boundary calculation.

    Returns:
        The new BudgetPeriodRecord, or None if no rollover is needed.
    """
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.is_active == True).first()
    if budget is None:
        return None

    current_period = get_active_period_record(db, budget_id)
    if current_period is None:
        return None

    today = date.today()

    # Only rollover if the period has ended
    if today <= current_period.period_end:
        return None

    # Mark the current period as completed
    if current_period.status == BudgetPeriodStatus.active:
        current_period.status = BudgetPeriodStatus.completed

    # Compute the new period boundaries starting from the day after the old period ends
    next_period_start = current_period.period_end + timedelta(days=1)

    if locale is None:
        from app.services.locale_service import LOCALE_CONFIGS
        locale = LOCALE_CONFIGS.get("US")

    period_start, period_end = _compute_period_boundaries(
        budget.period_type, next_period_start, locale
    )

    # Create the new period record with same limit (spent resets to 0)
    new_period = BudgetPeriodRecord(
        budget_id=budget.id,
        period_start=period_start,
        period_end=period_end,
        spent_smallest_unit=0,
        status=BudgetPeriodStatus.active,
    )
    db.add(new_period)
    db.commit()
    db.refresh(new_period)

    return new_period


def calculate_budget_projection(
    budget: Budget,
    period: BudgetPeriodRecord,
    today: Optional[date] = None,
) -> BudgetProjection:
    """Calculate the budget projection for the current period.

    Projects end-of-period spend based on daily run rate:
        projected_spend = (spent_so_far / days_elapsed) * total_days_in_period

    Args:
        budget: The Budget instance.
        period: The current BudgetPeriodRecord.
        today: Override for current date (defaults to date.today()).

    Returns:
        BudgetProjection with remaining, projected_spend, status, and overage.
    """
    if today is None:
        today = date.today()

    days_elapsed = (today - period.period_start).days
    total_days = (period.period_end - period.period_start).days + 1

    if days_elapsed == 0:
        return BudgetProjection(
            remaining=budget.limit_smallest_unit,
            projected_spend=0,
            status="on_track",
            overage=0,
        )

    daily_rate = period.spent_smallest_unit / days_elapsed
    projected_spend = int(daily_rate * total_days)
    remaining = budget.limit_smallest_unit - period.spent_smallest_unit

    if projected_spend > budget.limit_smallest_unit:
        return BudgetProjection(
            remaining=remaining,
            projected_spend=projected_spend,
            status="off_track",
            overage=projected_spend - budget.limit_smallest_unit,
        )

    return BudgetProjection(
        remaining=remaining,
        projected_spend=projected_spend,
        status="on_track",
        overage=0,
    )


def get_user_budgets(
    db: Session,
    user_id: int,
    active_only: bool = True,
) -> list[Budget]:
    """Get all budgets for a user.

    Args:
        db: Database session.
        user_id: The user's ID.
        active_only: If True, only return active budgets.

    Returns:
        List of Budget instances.
    """
    query = db.query(Budget).filter(Budget.user_id == user_id)
    if active_only:
        query = query.filter(Budget.is_active == True)
    return query.all()


def deactivate_budget(
    db: Session,
    budget_id: int,
    user_id: int,
) -> Optional[Budget]:
    """Deactivate a budget (soft delete).

    Args:
        db: Database session.
        budget_id: The budget's ID.
        user_id: The user's ID (for ownership check).

    Returns:
        The deactivated Budget, or None if not found.
    """
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user_id)
        .first()
    )
    if budget is None:
        return None

    budget.is_active = False
    db.commit()
    db.refresh(budget)
    return budget


def update_budget_limit(
    db: Session,
    budget_id: int,
    user_id: int,
    new_limit_smallest_unit: int,
    decimal_precision: int = 2,
) -> Optional[Budget]:
    """Update the spending limit of an existing budget.

    Args:
        db: Database session.
        budget_id: The budget's ID.
        user_id: The user's ID (for ownership check).
        new_limit_smallest_unit: The new positive integer limit.
        decimal_precision: Decimal precision for validation.

    Returns:
        The updated Budget, or None if not found.

    Raises:
        BudgetValidationError: If the new limit is invalid.
    """
    _validate_budget_limit(new_limit_smallest_unit, "", decimal_precision)

    budget = (
        db.query(Budget)
        .filter(
            Budget.id == budget_id,
            Budget.user_id == user_id,
            Budget.is_active == True,
        )
        .first()
    )
    if budget is None:
        return None

    budget.limit_smallest_unit = new_limit_smallest_unit
    db.commit()
    db.refresh(budget)
    return budget


def recalculate_on_income(
    db: Session,
    user_id: int,
    income_transaction: Transaction,
) -> list[BudgetLimitChangeLog]:
    """Recalculate active budget limits when income is received.

    For each active budget with a matching CategoryWeight entry, computes:
        new_limit = floor(weight_percentage / 100 × available_balance)

    Only updates budgets where new_limit differs from the current limit.
    Creates a BudgetLimitChangeLog entry atomically with each budget limit update.

    Does NOT modify stored CategoryWeight percentages.

    Args:
        db: Database session.
        user_id: The user's ID.
        income_transaction: The income Transaction that triggered recalculation.

    Returns:
        List of BudgetLimitChangeLog entries created for changed budgets.
    """
    # Compute available_balance = sum(received) - sum(spent) across all user transactions
    received_total = (
        db.query(func.coalesce(func.sum(Transaction.amount_smallest_unit), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.direction == TransactionDirection.received,
        )
        .scalar()
    )

    spent_total = (
        db.query(func.coalesce(func.sum(Transaction.amount_smallest_unit), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.direction == TransactionDirection.spent,
        )
        .scalar()
    )

    available_balance = received_total - spent_total

    # Get all active budgets for this user that have a category
    active_budgets = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.is_active == True,
        )
        .all()
    )

    # Get all CategoryWeight entries for this user, keyed by category_name
    weights = (
        db.query(CategoryWeight)
        .filter(CategoryWeight.user_id == user_id)
        .all()
    )
    weight_by_name: dict[str, Decimal] = {
        w.category_name: w.weight_percentage for w in weights
    }

    change_logs: list[BudgetLimitChangeLog] = []

    for budget in active_budgets:
        # Determine the category name for this budget
        if budget.category_id is None:
            # Overall budget — skip (no single weight applies)
            continue

        category = (
            db.query(Category)
            .filter(Category.id == budget.category_id)
            .first()
        )
        if category is None:
            continue

        # Check if there's a matching CategoryWeight entry
        weight_percentage = weight_by_name.get(category.name)
        if weight_percentage is None:
            continue

        # Calculate new limit: floor(weight_percentage / 100 × available_balance)
        new_limit = math.floor(
            float(weight_percentage) / 100.0 * available_balance
        )

        old_limit = budget.limit_smallest_unit

        # Only update if the limit actually changed
        if new_limit == old_limit:
            continue

        # Update budget limit and create change log atomically
        budget.limit_smallest_unit = new_limit

        reason = (
            f"Income received: {income_transaction.amount_smallest_unit} "
            f"from transaction #{income_transaction.id}"
        )

        change_log = BudgetLimitChangeLog(
            budget_id=budget.id,
            old_limit_smallest_unit=old_limit,
            new_limit_smallest_unit=new_limit,
            reason=reason,
            source_transaction_id=income_transaction.id,
        )
        db.add(change_log)
        change_logs.append(change_log)

    if change_logs:
        db.commit()
        for log in change_logs:
            db.refresh(log)

    return change_logs
