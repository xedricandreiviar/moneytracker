"""Tests for InsightEngine periodic summary generation.

Covers: generate_weekly_summary, generate_monthly_summary,
percentage change calculations, zero-activity periods,
first period handling, and "new" category marking.
"""

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.category import Category
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.services.insight_engine import (
    CategoryTotal,
    MonthlySummary,
    WeeklySummary,
    _calculate_percentage_change,
    _get_month_date_range,
    _get_prior_month,
    generate_monthly_summary,
    generate_weekly_summary,
)
from app.services.locale_service import LOCALE_CONFIGS


def _create_test_session() -> Session:
    """Create an in-memory SQLite engine and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession()


def _create_user(db: Session) -> User:
    """Helper to create a test user."""
    user = User(
        timezone="UTC",
        current_streak=0,
        created_at_utc=datetime.now(timezone.utc),
        version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_category(db: Session, user_id: int, name: str) -> Category:
    """Helper to create a category."""
    cat = Category(
        user_id=user_id,
        name=name,
        usage_count=1,
        last_used_at_utc=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _create_transaction(
    db: Session,
    user_id: int,
    amount: int,
    direction: str,
    local_date: date,
    category_id: int | None = None,
) -> Transaction:
    """Helper to create a transaction with a specific local date."""
    txn = Transaction(
        user_id=user_id,
        amount_smallest_unit=amount,
        direction=TransactionDirection(direction),
        currency_code="USD",
        category_id=category_id,
        transaction_datetime_utc=datetime.now(timezone.utc),
        transaction_date_local=local_date,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


US_LOCALE = LOCALE_CONFIGS["US"]


class TestCalculatePercentageChange:
    """Tests for _calculate_percentage_change helper."""

    def test_positive_change(self):
        """100 to 150 should be +50.0%."""
        assert _calculate_percentage_change(150, 100) == 50.0

    def test_negative_change(self):
        """100 to 75 should be -25.0%."""
        assert _calculate_percentage_change(75, 100) == -25.0

    def test_no_change(self):
        """Same value should be 0.0%."""
        assert _calculate_percentage_change(100, 100) == 0.0

    def test_previous_zero_returns_none(self):
        """Zero previous should return None (caller marks as 'new')."""
        assert _calculate_percentage_change(100, 0) is None

    def test_current_zero(self):
        """Current zero with nonzero previous should be -100.0%."""
        assert _calculate_percentage_change(0, 100) == -100.0

    def test_rounds_to_one_decimal(self):
        """Should round to 1 decimal place."""
        # 100 to 133 = 33.0%
        assert _calculate_percentage_change(133, 100) == 33.0
        # 100 to 166 = 66.0%
        assert _calculate_percentage_change(166, 100) == 66.0
        # 3 to 1 = -66.7% (1/3 remaining => -66.666...%)
        assert _calculate_percentage_change(1, 3) == -66.7


class TestGetMonthDateRange:
    """Tests for _get_month_date_range helper."""

    def test_january(self):
        """January should be 1st to 31st."""
        start, end = _get_month_date_range(1, 2024)
        assert start == date(2024, 1, 1)
        assert end == date(2024, 1, 31)

    def test_february_leap_year(self):
        """February in leap year should end on 29th."""
        start, end = _get_month_date_range(2, 2024)
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)

    def test_february_non_leap_year(self):
        """February in non-leap year should end on 28th."""
        start, end = _get_month_date_range(2, 2023)
        assert start == date(2023, 2, 1)
        assert end == date(2023, 2, 28)

    def test_december(self):
        """December should be 1st to 31st."""
        start, end = _get_month_date_range(12, 2024)
        assert start == date(2024, 12, 1)
        assert end == date(2024, 12, 31)


class TestGetPriorMonth:
    """Tests for _get_prior_month helper."""

    def test_mid_year(self):
        """March prior should be February same year."""
        assert _get_prior_month(3, 2024) == (2, 2024)

    def test_january_wraps_to_december(self):
        """January prior should be December prior year."""
        assert _get_prior_month(1, 2024) == (12, 2023)


class TestGenerateWeeklySummary:
    """Tests for generate_weekly_summary."""

    def test_basic_weekly_totals(self):
        """Should calculate correct spent, received, and net totals."""
        db = _create_test_session()
        user = _create_user(db)

        # Week: Jan 1-7, 2024
        _create_transaction(db, user.id, 1000, "spent", date(2024, 1, 2))
        _create_transaction(db, user.id, 500, "spent", date(2024, 1, 3))
        _create_transaction(db, user.id, 3000, "received", date(2024, 1, 4))

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        assert summary.total_spent == 1500
        assert summary.total_received == 3000
        assert summary.net == 1500  # received - spent
        assert summary.week_start == date(2024, 1, 1)
        assert summary.week_end == date(2024, 1, 7)
        db.close()

    def test_category_breakdown(self):
        """Should break down totals by category."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")
        transport = _create_category(db, user.id, "Transport")

        _create_transaction(db, user.id, 500, "spent", date(2024, 1, 2), food.id)
        _create_transaction(db, user.id, 300, "spent", date(2024, 1, 3), food.id)
        _create_transaction(db, user.id, 200, "spent", date(2024, 1, 4), transport.id)

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        assert summary.total_spent == 1000
        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert "Food" in cat_map
        assert cat_map["Food"].total_spent == 800
        assert "Transport" in cat_map
        assert cat_map["Transport"].total_spent == 200
        db.close()

    def test_percentage_change_vs_prior_week(self):
        """Should calculate percentage change compared to prior week."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")

        # Prior week (Dec 25-31): $10.00 on food
        _create_transaction(db, user.id, 1000, "spent", date(2023, 12, 26), food.id)

        # Current week (Jan 1-7): $15.00 on food
        _create_transaction(db, user.id, 1500, "spent", date(2024, 1, 2), food.id)

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Food"].percentage_change == 50.0
        assert cat_map["Food"].is_new is False
        assert summary.has_prior_period is True
        db.close()

    def test_new_category_marker(self):
        """Category with zero in prior but spending in current should be marked 'new'."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")
        entertainment = _create_category(db, user.id, "Entertainment")

        # Prior week: only Food
        _create_transaction(db, user.id, 1000, "spent", date(2023, 12, 26), food.id)

        # Current week: Food + Entertainment (new)
        _create_transaction(db, user.id, 800, "spent", date(2024, 1, 2), food.id)
        _create_transaction(db, user.id, 500, "spent", date(2024, 1, 3), entertainment.id)

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Entertainment"].is_new is True
        assert cat_map["Entertainment"].percentage_change is None
        db.close()

    def test_zero_activity_period(self):
        """Zero-activity period should generate summary with zero values (Req 5.5)."""
        db = _create_test_session()
        user = _create_user(db)

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        assert summary.total_spent == 0
        assert summary.total_received == 0
        assert summary.net == 0
        assert summary.category_totals == []
        db.close()

    def test_first_period_no_comparison(self):
        """First week should indicate no prior period available (Req 5.7)."""
        db = _create_test_session()
        user = _create_user(db)

        # Only current week has data, prior week is empty
        _create_transaction(db, user.id, 500, "spent", date(2024, 1, 2))

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        assert summary.has_prior_period is False
        # Category totals should have no percentage change
        for ct in summary.category_totals:
            assert ct.percentage_change is None
            assert ct.is_new is False
        db.close()

    def test_transactions_outside_week_excluded(self):
        """Transactions outside the week boundaries should be excluded."""
        db = _create_test_session()
        user = _create_user(db)

        # Inside week (Jan 1-7)
        _create_transaction(db, user.id, 500, "spent", date(2024, 1, 3))
        # Outside week (before)
        _create_transaction(db, user.id, 999, "spent", date(2023, 12, 31))
        # Outside week (after)
        _create_transaction(db, user.id, 888, "spent", date(2024, 1, 8))

        summary = generate_weekly_summary(db, user.id, date(2024, 1, 7), US_LOCALE)

        assert summary.total_spent == 500
        db.close()


class TestGenerateMonthlySummary:
    """Tests for generate_monthly_summary."""

    def test_basic_monthly_totals(self):
        """Should calculate correct monthly spent, received, and net."""
        db = _create_test_session()
        user = _create_user(db)

        _create_transaction(db, user.id, 2000, "spent", date(2024, 1, 5))
        _create_transaction(db, user.id, 3000, "spent", date(2024, 1, 15))
        _create_transaction(db, user.id, 10000, "received", date(2024, 1, 25))

        summary = generate_monthly_summary(db, user.id, 1, 2024, US_LOCALE)

        assert summary.total_spent == 5000
        assert summary.total_received == 10000
        assert summary.net == 5000
        assert summary.month == 1
        assert summary.year == 2024
        db.close()

    def test_monthly_category_breakdown(self):
        """Should break down monthly totals by category."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")
        rent = _create_category(db, user.id, "Rent")

        _create_transaction(db, user.id, 5000, "spent", date(2024, 2, 5), food.id)
        _create_transaction(db, user.id, 100000, "spent", date(2024, 2, 1), rent.id)

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Food"].total_spent == 5000
        assert cat_map["Rent"].total_spent == 100000
        db.close()

    def test_monthly_percentage_change_vs_prior(self):
        """Should calculate percentage change vs prior month."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")

        # January: $100 food
        _create_transaction(db, user.id, 10000, "spent", date(2024, 1, 15), food.id)
        # February: $120 food (+20%)
        _create_transaction(db, user.id, 12000, "spent", date(2024, 2, 15), food.id)

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Food"].percentage_change == 20.0
        assert summary.has_prior_period is True
        db.close()

    def test_monthly_absolute_change(self):
        """Should include absolute difference vs prior month."""
        db = _create_test_session()
        user = _create_user(db)

        # January totals
        _create_transaction(db, user.id, 10000, "spent", date(2024, 1, 15))
        _create_transaction(db, user.id, 50000, "received", date(2024, 1, 15))

        # February totals
        _create_transaction(db, user.id, 12000, "spent", date(2024, 2, 15))
        _create_transaction(db, user.id, 45000, "received", date(2024, 2, 15))

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        assert summary.total_spent_abs_change == 2000  # 12000 - 10000
        assert summary.total_received_abs_change == -5000  # 45000 - 50000
        assert summary.total_spent_change == 20.0
        assert summary.total_received_change == -10.0
        db.close()

    def test_monthly_new_category_marker(self):
        """New categories in current month should be marked 'new'."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")
        gym = _create_category(db, user.id, "Gym")

        # January: only food
        _create_transaction(db, user.id, 5000, "spent", date(2024, 1, 10), food.id)

        # February: food + gym (new)
        _create_transaction(db, user.id, 4000, "spent", date(2024, 2, 10), food.id)
        _create_transaction(db, user.id, 3000, "spent", date(2024, 2, 10), gym.id)

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Gym"].is_new is True
        assert cat_map["Gym"].percentage_change is None
        assert cat_map["Food"].is_new is False
        assert cat_map["Food"].percentage_change == -20.0
        db.close()

    def test_monthly_zero_activity(self):
        """Zero-activity month should generate summary with zero values."""
        db = _create_test_session()
        user = _create_user(db)

        summary = generate_monthly_summary(db, user.id, 3, 2024, US_LOCALE)

        assert summary.total_spent == 0
        assert summary.total_received == 0
        assert summary.net == 0
        assert summary.category_totals == []
        db.close()

    def test_monthly_first_period_no_comparison(self):
        """First month should indicate no prior period (Req 5.7)."""
        db = _create_test_session()
        user = _create_user(db)

        # Only February has data
        _create_transaction(db, user.id, 5000, "spent", date(2024, 2, 10))

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        assert summary.has_prior_period is False
        assert summary.total_spent_change is None
        assert summary.total_received_change is None
        assert summary.total_spent_abs_change is None
        assert summary.total_received_abs_change is None
        db.close()

    def test_monthly_january_compares_to_december(self):
        """January should compare against prior year's December."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")

        # December 2023: $80.00
        _create_transaction(db, user.id, 8000, "spent", date(2023, 12, 15), food.id)
        # January 2024: $100.00 (+25%)
        _create_transaction(db, user.id, 10000, "spent", date(2024, 1, 15), food.id)

        summary = generate_monthly_summary(db, user.id, 1, 2024, US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert cat_map["Food"].percentage_change == 25.0
        assert summary.has_prior_period is True
        db.close()

    def test_transactions_outside_month_excluded(self):
        """Transactions outside the target month should be excluded."""
        db = _create_test_session()
        user = _create_user(db)

        # Inside February 2024
        _create_transaction(db, user.id, 500, "spent", date(2024, 2, 15))
        # Outside (January)
        _create_transaction(db, user.id, 999, "spent", date(2024, 1, 31))
        # Outside (March)
        _create_transaction(db, user.id, 888, "spent", date(2024, 3, 1))

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        assert summary.total_spent == 500
        db.close()

    def test_uncategorized_transactions_grouped(self):
        """Transactions without a category should appear as 'Uncategorized'."""
        db = _create_test_session()
        user = _create_user(db)

        food = _create_category(db, user.id, "Food")
        _create_transaction(db, user.id, 500, "spent", date(2024, 2, 5), food.id)
        _create_transaction(db, user.id, 300, "spent", date(2024, 2, 10), None)

        summary = generate_monthly_summary(db, user.id, 2, 2024, US_LOCALE)

        cat_map = {ct.category_name: ct for ct in summary.category_totals}
        assert "Food" in cat_map
        assert "Uncategorized" in cat_map
        assert cat_map["Uncategorized"].total_spent == 300
        db.close()
