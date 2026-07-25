"""Tests for BudgetService.

Covers: budget creation, validation, uniqueness enforcement,
period record tracking, auto-rollover, and projection calculations.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.budget import (
    Budget,
    BudgetPeriodRecord,
    BudgetPeriodStatus,
    BudgetPeriodType,
)
from app.models.user import User
from app.services.budget_service import (
    BudgetConflictError,
    BudgetProjection,
    BudgetValidationError,
    calculate_budget_projection,
    create_budget,
    deactivate_budget,
    get_active_period_record,
    rollover_period,
    update_budget_limit,
    update_spent,
)
from app.services.locale_service import LOCALE_CONFIGS, LocaleConfig


def _create_test_session():
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


US_LOCALE = LOCALE_CONFIGS["US"]
JP_LOCALE = LOCALE_CONFIGS["JP"]


class TestBudgetCreationValidation:
    """Tests for budget limit validation (Req 8.8)."""

    def test_valid_limit_creates_budget(self):
        """Positive integer limit should succeed."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        assert budget.id is not None
        assert budget.limit_smallest_unit == 50000
        assert budget.period_type == BudgetPeriodType.monthly
        assert budget.is_active is True
        assert budget.currency_code == "USD"
        db.close()

    def test_zero_limit_raises(self):
        """Zero limit should raise BudgetValidationError (Req 8.8)."""
        db = _create_test_session()
        user = _create_user(db)

        try:
            create_budget(
                db=db,
                user_id=user.id,
                period_type="monthly",
                limit_smallest_unit=0,
                currency_code="USD",
                locale=US_LOCALE,
            )
            assert False, "Expected BudgetValidationError"
        except BudgetValidationError as e:
            assert e.field == "limit"
            assert "positive" in e.message.lower()
        db.close()

    def test_negative_limit_raises(self):
        """Negative limit should raise BudgetValidationError (Req 8.8)."""
        db = _create_test_session()
        user = _create_user(db)

        try:
            create_budget(
                db=db,
                user_id=user.id,
                period_type="weekly",
                limit_smallest_unit=-100,
                currency_code="USD",
                locale=US_LOCALE,
            )
            assert False, "Expected BudgetValidationError"
        except BudgetValidationError as e:
            assert e.field == "limit"
        db.close()

    def test_non_integer_limit_raises(self):
        """Non-integer limit should raise BudgetValidationError."""
        db = _create_test_session()
        user = _create_user(db)

        try:
            create_budget(
                db=db,
                user_id=user.id,
                period_type="monthly",
                limit_smallest_unit=10.5,  # type: ignore
                currency_code="USD",
                locale=US_LOCALE,
            )
            assert False, "Expected BudgetValidationError"
        except BudgetValidationError as e:
            assert e.field == "limit"
        db.close()

    def test_invalid_period_type_raises(self):
        """Invalid period type should raise BudgetValidationError."""
        db = _create_test_session()
        user = _create_user(db)

        try:
            create_budget(
                db=db,
                user_id=user.id,
                period_type="daily",
                limit_smallest_unit=5000,
                currency_code="USD",
                locale=US_LOCALE,
            )
            assert False, "Expected BudgetValidationError"
        except BudgetValidationError as e:
            assert e.field == "period_type"
        db.close()

    def test_currency_code_uppercased(self):
        """Currency code should be stored uppercase."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=10000,
            currency_code="usd",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        assert budget.currency_code == "USD"
        db.close()


class TestBudgetUniqueness:
    """Tests for budget uniqueness enforcement (Req 8.7)."""

    def test_duplicate_same_category_and_period_raises(self):
        """Creating duplicate budget for same category/period should fail."""
        db = _create_test_session()
        user = _create_user(db)

        create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        try:
            create_budget(
                db=db,
                user_id=user.id,
                period_type="monthly",
                limit_smallest_unit=30000,
                currency_code="USD",
                locale=US_LOCALE,
                reference_date=date(2024, 3, 15),
            )
            assert False, "Expected BudgetConflictError"
        except BudgetConflictError as e:
            assert "already exists" in e.message.lower()
        db.close()

    def test_different_period_types_allowed(self):
        """Same category but different period types should be allowed."""
        db = _create_test_session()
        user = _create_user(db)

        b1 = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        b2 = create_budget(
            db=db,
            user_id=user.id,
            period_type="weekly",
            limit_smallest_unit=12000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        assert b1.id != b2.id
        db.close()

    def test_deactivated_budget_allows_new_creation(self):
        """Creating budget after deactivating the old one should succeed."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        deactivate_budget(db, budget.id, user.id)

        # Should now be able to create a new one
        new_budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=60000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )
        assert new_budget.id is not None
        assert new_budget.limit_smallest_unit == 60000
        db.close()


class TestBudgetPeriodRecord:
    """Tests for BudgetPeriodRecord tracking."""

    def test_initial_period_record_created(self):
        """Budget creation should create an initial period record."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        period = get_active_period_record(db, budget.id)
        assert period is not None
        assert period.spent_smallest_unit == 0
        assert period.status == BudgetPeriodStatus.active
        assert period.period_start == date(2024, 3, 1)
        assert period.period_end == date(2024, 3, 31)
        db.close()

    def test_weekly_period_boundaries(self):
        """Weekly budget should have correct week boundaries."""
        db = _create_test_session()
        user = _create_user(db)

        # US locale: week starts on Sunday
        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="weekly",
            limit_smallest_unit=20000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 13),  # Wednesday
        )

        period = get_active_period_record(db, budget.id)
        assert period is not None
        # Week containing Wed March 13, 2024 with Sunday start
        # Sunday March 10 to Saturday March 16
        assert period.period_start == date(2024, 3, 10)
        assert period.period_end == date(2024, 3, 16)
        db.close()

    def test_update_spent_on_transaction(self):
        """update_spent should increment the spent amount."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        # Log first transaction
        period = update_spent(db, budget.id, 1500)
        assert period is not None
        assert period.spent_smallest_unit == 1500

        # Log second transaction
        period = update_spent(db, budget.id, 2000)
        assert period.spent_smallest_unit == 3500
        db.close()

    def test_update_spent_marks_exceeded(self):
        """Spending over limit should mark period as exceeded."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=5000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        period = update_spent(db, budget.id, 6000)
        assert period is not None
        assert period.status == BudgetPeriodStatus.exceeded
        db.close()


class TestAutoRollover:
    """Tests for budget period auto-rollover (Req 8.6)."""

    def test_rollover_creates_new_period_when_current_ended(self):
        """Should create new period with same limit when period ends."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 2, 15),
        )

        # Simulate end of February period
        period = get_active_period_record(db, budget.id)
        assert period.period_end == date(2024, 2, 29)  # Leap year

        # Manually set period_end in the past to simulate rollover
        period.period_end = date(2024, 2, 29)
        db.commit()

        # Mock today as March 1 by patching
        from unittest.mock import patch
        with patch("app.services.budget_service.date") as mock_date:
            mock_date.today.return_value = date(2024, 3, 1)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            new_period = rollover_period(db, budget.id, locale=US_LOCALE)

        assert new_period is not None
        assert new_period.period_start == date(2024, 3, 1)
        assert new_period.period_end == date(2024, 3, 31)
        assert new_period.spent_smallest_unit == 0
        assert new_period.status == BudgetPeriodStatus.active

        # Old period should be marked completed
        old_period = (
            db.query(BudgetPeriodRecord)
            .filter(BudgetPeriodRecord.id == period.id)
            .first()
        )
        assert old_period.status == BudgetPeriodStatus.completed
        db.close()

    def test_no_rollover_when_period_not_ended(self):
        """Should not rollover if current period hasn't ended."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        # Today is within the period, so no rollover
        from unittest.mock import patch
        with patch("app.services.budget_service.date") as mock_date:
            mock_date.today.return_value = date(2024, 3, 20)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            result = rollover_period(db, budget.id, locale=US_LOCALE)

        assert result is None
        db.close()

    def test_rollover_inactive_budget_returns_none(self):
        """Inactive budget should not rollover."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 2, 15),
        )

        deactivate_budget(db, budget.id, user.id)

        from unittest.mock import patch
        with patch("app.services.budget_service.date") as mock_date:
            mock_date.today.return_value = date(2024, 3, 5)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            result = rollover_period(db, budget.id, locale=US_LOCALE)

        assert result is None
        db.close()


class TestBudgetProjection:
    """Tests for budget projection calculation (Req 7.1, 7.3, 7.4, 7.5)."""

    def test_zero_days_elapsed_on_track(self):
        """Zero days elapsed: on_track, remaining = full limit (Req 7.5)."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31),
            spent_smallest_unit=0,
            status=BudgetPeriodStatus.active,
        )

        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 1)
        )

        assert projection.status == "on_track"
        assert projection.remaining == 100000
        assert projection.projected_spend == 0
        assert projection.overage == 0

    def test_on_track_projection(self):
        """Projected spend <= limit should be on_track (Req 7.4)."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31),
            spent_smallest_unit=10000,  # Spent 10000 in 10 days
            status=BudgetPeriodStatus.active,
        )

        # 10 days elapsed, 31 total days
        # daily_rate = 10000/10 = 1000
        # projected = 1000 * 31 = 31000 <= 100000
        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 11)
        )

        assert projection.status == "on_track"
        assert projection.projected_spend == 31000
        assert projection.remaining == 90000  # 100000 - 10000
        assert projection.overage == 0

    def test_off_track_projection(self):
        """Projected spend > limit should be off_track (Req 7.3)."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=50000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31),
            spent_smallest_unit=30000,  # Spent 30000 in 10 days
            status=BudgetPeriodStatus.active,
        )

        # 10 days elapsed, 31 total days
        # daily_rate = 30000/10 = 3000
        # projected = 3000 * 31 = 93000 > 50000
        # overage = 93000 - 50000 = 43000
        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 11)
        )

        assert projection.status == "off_track"
        assert projection.projected_spend == 93000
        assert projection.remaining == 20000  # 50000 - 30000
        assert projection.overage == 43000

    def test_remaining_is_limit_minus_spent(self):
        """Remaining should be budget limit minus current spent (Req 7.1)."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.weekly,
            limit_smallest_unit=20000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 10),
            period_end=date(2024, 3, 16),
            spent_smallest_unit=8000,
            status=BudgetPeriodStatus.active,
        )

        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 14)
        )

        assert projection.remaining == 12000  # 20000 - 8000

    def test_projection_with_weekly_budget(self):
        """Weekly budget projection with correct total_days."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.weekly,
            limit_smallest_unit=14000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 10),  # Sunday
            period_end=date(2024, 3, 16),  # Saturday
            spent_smallest_unit=6000,  # Spent 6000 in 3 days
            status=BudgetPeriodStatus.active,
        )

        # 3 days elapsed, 7 total days
        # daily_rate = 6000/3 = 2000
        # projected = 2000 * 7 = 14000 == limit → on_track
        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 13)
        )

        assert projection.status == "on_track"
        assert projection.projected_spend == 14000
        assert projection.overage == 0

    def test_exactly_at_limit_is_on_track(self):
        """Projected spend exactly at limit should be on_track."""
        budget = Budget(
            id=1,
            user_id=1,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=31000,
            currency_code="USD",
            is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1,
            budget_id=1,
            period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31),
            spent_smallest_unit=1000,  # 1000 in 1 day
            status=BudgetPeriodStatus.active,
        )

        # 1 day elapsed, 31 total
        # projected = (1000/1) * 31 = 31000 == 31000 (not > limit)
        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 2)
        )

        assert projection.status == "on_track"
        assert projection.projected_spend == 31000
        assert projection.overage == 0


class TestUpdateBudgetLimit:
    """Tests for updating budget limit."""

    def test_update_limit_succeeds(self):
        """Should update the limit of an active budget."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        updated = update_budget_limit(db, budget.id, user.id, 75000)
        assert updated is not None
        assert updated.limit_smallest_unit == 75000
        db.close()

    def test_update_limit_invalid_raises(self):
        """Invalid new limit should raise."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        try:
            update_budget_limit(db, budget.id, user.id, -1000)
            assert False, "Expected BudgetValidationError"
        except BudgetValidationError:
            pass
        db.close()

    def test_update_nonexistent_budget_returns_none(self):
        """Updating non-existent budget should return None."""
        db = _create_test_session()
        user = _create_user(db)

        result = update_budget_limit(db, 9999, user.id, 50000)
        assert result is None
        db.close()


class TestDeactivateBudget:
    """Tests for budget deactivation."""

    def test_deactivate_budget(self):
        """Should set is_active to False."""
        db = _create_test_session()
        user = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        result = deactivate_budget(db, budget.id, user.id)
        assert result is not None
        assert result.is_active is False
        db.close()

    def test_deactivate_wrong_user_returns_none(self):
        """Should not deactivate budget owned by another user."""
        db = _create_test_session()
        user1 = _create_user(db)
        user2 = _create_user(db)

        budget = create_budget(
            db=db,
            user_id=user1.id,
            period_type="monthly",
            limit_smallest_unit=50000,
            currency_code="USD",
            locale=US_LOCALE,
            reference_date=date(2024, 3, 15),
        )

        result = deactivate_budget(db, budget.id, user2.id)
        assert result is None
        db.close()
