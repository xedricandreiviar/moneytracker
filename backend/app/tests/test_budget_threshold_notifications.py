"""Tests for budget threshold notifications (Requirements 8.3, 8.4).

Covers:
- 80% threshold notification fires exactly once per budget period
- 100% threshold notification fires exactly once per budget period
- Multiple transactions crossing the same threshold don't create duplicates
- Idempotency key prevents duplicate notifications
"""

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus, BudgetPeriodType
from app.models.notification import Notification
from app.models.user import User
from app.services.budget_service import check_budget_thresholds, update_spent


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


def _create_budget_with_period(
    db: Session,
    user_id: int,
    limit: int,
    spent: int = 0,
    period_start: date = date(2024, 1, 1),
    period_end: date = date(2024, 1, 31),
) -> tuple[Budget, BudgetPeriodRecord]:
    """Helper to create a budget with an active period record."""
    budget = Budget(
        user_id=user_id,
        category_id=None,
        period_type=BudgetPeriodType.monthly,
        limit_smallest_unit=limit,
        currency_code="USD",
        is_active=True,
    )
    db.add(budget)
    db.flush()

    period = BudgetPeriodRecord(
        budget_id=budget.id,
        period_start=period_start,
        period_end=period_end,
        spent_smallest_unit=spent,
        status=BudgetPeriodStatus.active,
    )
    db.add(period)
    db.commit()
    db.refresh(budget)
    db.refresh(period)
    return budget, period


class TestCheckBudgetThresholds:
    """Tests for check_budget_thresholds."""

    def test_no_notification_below_80_percent(self):
        """No notification should fire when spending is below 80%."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=7999)

        notifications = check_budget_thresholds(db, budget.id)

        assert notifications == []
        assert db.query(Notification).count() == 0
        db.close()

    def test_80_percent_notification_fires_at_threshold(self):
        """80% notification should fire when spending reaches exactly 80%."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=8000)

        notifications = check_budget_thresholds(db, budget.id)

        assert len(notifications) == 1
        assert notifications[0].notification_type == "budget_80"
        assert notifications[0].user_id == user.id
        assert "80%" in notifications[0].body
        db.close()

    def test_80_percent_notification_fires_above_threshold(self):
        """80% notification should fire when spending exceeds 80%."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=8500)

        notifications = check_budget_thresholds(db, budget.id)

        # Should fire 80% notification (but not 100% since we're below 100%)
        types = [n.notification_type for n in notifications]
        assert "budget_80" in types
        assert "budget_100" not in types
        db.close()

    def test_100_percent_notification_fires_at_threshold(self):
        """100% notification should fire when spending reaches exactly 100%."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=10000)

        notifications = check_budget_thresholds(db, budget.id)

        # Both 80% and 100% should fire since spending >= both thresholds
        types = [n.notification_type for n in notifications]
        assert "budget_80" in types
        assert "budget_100" in types
        assert len(notifications) == 2
        db.close()

    def test_100_percent_notification_fires_above_threshold(self):
        """100% notification should fire when spending exceeds 100%."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=12000)

        notifications = check_budget_thresholds(db, budget.id)

        types = [n.notification_type for n in notifications]
        assert "budget_80" in types
        assert "budget_100" in types
        db.close()

    def test_80_percent_notification_fires_exactly_once(self):
        """80% threshold notification should fire exactly once per budget period."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=8000)

        # First check - should fire
        notifications1 = check_budget_thresholds(db, budget.id)
        assert len(notifications1) == 1
        assert notifications1[0].notification_type == "budget_80"

        # Second check - should NOT fire again (idempotency)
        notifications2 = check_budget_thresholds(db, budget.id)
        assert len(notifications2) == 0

        # Verify only one notification exists in total
        all_notifications = db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(all_notifications) == 1
        db.close()

    def test_100_percent_notification_fires_exactly_once(self):
        """100% threshold notification should fire exactly once per budget period."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=10000)

        # First check - should fire
        notifications1 = check_budget_thresholds(db, budget.id)
        budget_100_notifs = [n for n in notifications1 if n.notification_type == "budget_100"]
        assert len(budget_100_notifs) == 1

        # Second check - should NOT fire again
        notifications2 = check_budget_thresholds(db, budget.id)
        assert len(notifications2) == 0

        # Verify only one 100% notification exists
        all_100 = db.query(Notification).filter(
            Notification.notification_type == "budget_100"
        ).all()
        assert len(all_100) == 1
        db.close()

    def test_multiple_transactions_no_duplicate_notifications(self):
        """Multiple transactions crossing the same threshold don't create duplicates."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=7000)

        # First transaction pushes to 80%
        update_spent(db, budget.id, 1000)  # Now at 8000 (80%)
        notifs_80 = db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(notifs_80) == 1

        # Second transaction still above 80%
        update_spent(db, budget.id, 500)  # Now at 8500
        notifs_80 = db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(notifs_80) == 1  # Still just one

        # Third transaction pushes to 100%
        update_spent(db, budget.id, 1500)  # Now at 10000 (100%)
        notifs_100 = db.query(Notification).filter(
            Notification.notification_type == "budget_100"
        ).all()
        assert len(notifs_100) == 1

        # Fourth transaction exceeds 100% further
        update_spent(db, budget.id, 2000)  # Now at 12000
        notifs_100 = db.query(Notification).filter(
            Notification.notification_type == "budget_100"
        ).all()
        assert len(notifs_100) == 1  # Still just one

        # Verify total notifications: 1 for 80%, 1 for 100%
        total = db.query(Notification).count()
        assert total == 2
        db.close()

    def test_different_periods_get_separate_notifications(self):
        """Notifications in different budget periods are independent."""
        db = _create_test_session()
        user = _create_user(db)

        # First period
        budget = Budget(
            user_id=user.id,
            category_id=None,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=10000,
            currency_code="USD",
            is_active=True,
        )
        db.add(budget)
        db.flush()

        period1 = BudgetPeriodRecord(
            budget_id=budget.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            spent_smallest_unit=8000,
            status=BudgetPeriodStatus.active,
        )
        db.add(period1)
        db.commit()

        # Fire notification for first period
        notifications1 = check_budget_thresholds(db, budget.id)
        assert len(notifications1) == 1

        # Mark first period completed and create new period
        period1.status = BudgetPeriodStatus.completed
        period2 = BudgetPeriodRecord(
            budget_id=budget.id,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            spent_smallest_unit=8000,
            status=BudgetPeriodStatus.active,
        )
        db.add(period2)
        db.commit()

        # Fire notification for second period - should work independently
        notifications2 = check_budget_thresholds(db, budget.id)
        assert len(notifications2) == 1

        # Total should be 2 (one per period)
        all_80 = db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(all_80) == 2
        db.close()

    def test_idempotency_key_in_payload(self):
        """Notification payload should contain the idempotency key."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user.id, limit=10000, spent=8000,
            period_start=date(2024, 3, 1),
        )

        notifications = check_budget_thresholds(db, budget.id)

        assert len(notifications) == 1
        expected_key = f"{budget.id}_2024-03-01_80"
        assert expected_key in notifications[0].payload_json
        db.close()

    def test_nonexistent_budget_returns_empty(self):
        """check_budget_thresholds with non-existent budget ID returns empty."""
        db = _create_test_session()
        # Don't create any budget
        notifications = check_budget_thresholds(db, 999)
        assert notifications == []
        db.close()

    def test_budget_without_active_period_returns_empty(self):
        """Budget with no active period should return empty notifications."""
        db = _create_test_session()
        user = _create_user(db)
        budget = Budget(
            user_id=user.id,
            category_id=None,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=10000,
            currency_code="USD",
            is_active=True,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)

        notifications = check_budget_thresholds(db, budget.id)
        assert notifications == []
        db.close()

    def test_update_spent_triggers_threshold_check(self):
        """update_spent should automatically trigger threshold notification."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(db, user.id, limit=10000, spent=7500)

        # This transaction pushes spending to 8000 (80%)
        update_spent(db, budget.id, 500)

        # Notification should have been created automatically
        notifs = db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(notifs) == 1
        db.close()
