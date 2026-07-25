"""Tests for DailyTaskService.

Covers: generate_daily_task, complete_task, get_current_task,
check_grace_period, auto_complete_on_transaction.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.daily_task import DailyTask, DailyTaskCompletionType, DailyTaskStatus
from app.models.user import User
from app.services.daily_task_service import (
    CurrentTaskInfo,
    DailyTaskError,
    GracePeriodStatus,
    auto_complete_on_transaction,
    check_grace_period,
    complete_task,
    generate_daily_task,
    get_current_task,
)


def _create_test_session() -> Session:
    """Create an in-memory SQLite engine and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession()


def _create_user(db: Session, timezone_str: str = "UTC") -> User:
    """Helper to create a test user."""
    user = User(
        timezone=timezone_str,
        current_streak=0,
        created_at_utc=datetime.now(timezone.utc),
        version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestGenerateDailyTask:
    """Tests for generate_daily_task."""

    def test_creates_pending_task_for_date(self):
        """Should create a pending task for the specified date."""
        db = _create_test_session()
        user = _create_user(db)
        task_date = date(2024, 6, 15)

        task = generate_daily_task(db, user.id, task_date)

        assert task.id is not None
        assert task.user_id == user.id
        assert task.task_date == task_date
        assert task.status == DailyTaskStatus.pending
        assert task.completion_type is None
        assert task.completed_at_utc is None
        assert task.created_at_utc is not None
        db.close()

    def test_idempotent_returns_existing_task(self):
        """Should return existing task if one already exists for that date."""
        db = _create_test_session()
        user = _create_user(db)
        task_date = date(2024, 6, 15)

        task1 = generate_daily_task(db, user.id, task_date)
        task2 = generate_daily_task(db, user.id, task_date)

        assert task1.id == task2.id
        db.close()

    def test_different_dates_create_different_tasks(self):
        """Should create separate tasks for different dates."""
        db = _create_test_session()
        user = _create_user(db)

        task1 = generate_daily_task(db, user.id, date(2024, 6, 15))
        task2 = generate_daily_task(db, user.id, date(2024, 6, 16))

        assert task1.id != task2.id
        assert task1.task_date == date(2024, 6, 15)
        assert task2.task_date == date(2024, 6, 16)
        db.close()

    def test_raises_for_nonexistent_user(self):
        """Should raise DailyTaskError when user doesn't exist."""
        db = _create_test_session()

        try:
            generate_daily_task(db, 9999, date(2024, 6, 15))
            assert False, "Expected DailyTaskError"
        except DailyTaskError as e:
            assert "not found" in e.message.lower()
        db.close()

    def test_uses_provided_now_utc(self):
        """Should use provided now_utc for created_at_utc."""
        db = _create_test_session()
        user = _create_user(db)
        custom_now = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

        task = generate_daily_task(db, user.id, date(2024, 6, 15), now_utc=custom_now)

        # SQLite strips tzinfo, so compare naive datetimes
        assert task.created_at_utc.replace(tzinfo=None) == custom_now.replace(tzinfo=None)
        db.close()


class TestCompleteTask:
    """Tests for complete_task."""

    def test_complete_pending_task_with_no_transactions(self):
        """Should transition pending → completed with no_transactions."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))

        completed = complete_task(db, task.id, "no_transactions")

        assert completed.status == DailyTaskStatus.completed
        assert completed.completion_type == DailyTaskCompletionType.no_transactions
        assert completed.completed_at_utc is not None
        db.close()

    def test_complete_pending_task_with_transaction_logged(self):
        """Should transition pending → completed with transaction_logged."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))

        completed = complete_task(db, task.id, "transaction_logged")

        assert completed.status == DailyTaskStatus.completed
        assert completed.completion_type == DailyTaskCompletionType.transaction_logged
        db.close()

    def test_complete_grace_period_task(self):
        """Should transition grace_period → completed with grace_recovery."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))

        # Manually set to grace_period
        task.status = DailyTaskStatus.grace_period
        db.commit()

        completed = complete_task(db, task.id, "grace_recovery")

        assert completed.status == DailyTaskStatus.completed
        assert completed.completion_type == DailyTaskCompletionType.grace_recovery
        db.close()

    def test_increments_streak_on_completion(self):
        """Should increment the user's streak by 1 on completion."""
        db = _create_test_session()
        user = _create_user(db)
        assert user.current_streak == 0

        task = generate_daily_task(db, user.id, date(2024, 6, 15))
        complete_task(db, task.id, "transaction_logged")

        db.refresh(user)
        assert user.current_streak == 1
        db.close()

    def test_increments_streak_multiple_completions(self):
        """Streak should increment for each completed task."""
        db = _create_test_session()
        user = _create_user(db)

        task1 = generate_daily_task(db, user.id, date(2024, 6, 15))
        complete_task(db, task1.id, "transaction_logged")

        task2 = generate_daily_task(db, user.id, date(2024, 6, 16))
        complete_task(db, task2.id, "no_transactions")

        db.refresh(user)
        assert user.current_streak == 2
        db.close()

    def test_raises_for_nonexistent_task(self):
        """Should raise DailyTaskError for nonexistent task ID."""
        db = _create_test_session()

        try:
            complete_task(db, 9999, "no_transactions")
            assert False, "Expected DailyTaskError"
        except DailyTaskError as e:
            assert "not found" in e.message.lower()
        db.close()

    def test_raises_for_invalid_completion_type(self):
        """Should raise DailyTaskError for invalid completion_type."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))

        try:
            complete_task(db, task.id, "invalid_type")
            assert False, "Expected DailyTaskError"
        except DailyTaskError as e:
            assert "invalid" in e.message.lower()
        db.close()

    def test_raises_for_already_completed_task(self):
        """Should raise DailyTaskError for already completed task."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))
        complete_task(db, task.id, "no_transactions")

        try:
            complete_task(db, task.id, "transaction_logged")
            assert False, "Expected DailyTaskError"
        except DailyTaskError as e:
            assert "cannot complete" in e.message.lower()
        db.close()

    def test_raises_for_missed_task(self):
        """Should raise DailyTaskError for missed task."""
        db = _create_test_session()
        user = _create_user(db)
        task = generate_daily_task(db, user.id, date(2024, 6, 15))

        # Manually set to missed
        task.status = DailyTaskStatus.missed
        db.commit()

        try:
            complete_task(db, task.id, "no_transactions")
            assert False, "Expected DailyTaskError"
        except DailyTaskError as e:
            assert "cannot complete" in e.message.lower()
        db.close()

    def test_updates_streak_last_updated_utc(self):
        """Should update streak_last_updated_utc on completion."""
        db = _create_test_session()
        user = _create_user(db)
        custom_now = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

        task = generate_daily_task(db, user.id, date(2024, 6, 15))
        complete_task(db, task.id, "no_transactions", now_utc=custom_now)

        db.refresh(user)
        # SQLite strips tzinfo, so compare naive datetimes
        assert user.streak_last_updated_utc.replace(tzinfo=None) == custom_now.replace(tzinfo=None)
        db.close()


class TestGetCurrentTask:
    """Tests for get_current_task."""

    def test_returns_todays_task(self):
        """Should return today's task with hours remaining."""
        db = _create_test_session()
        user = _create_user(db)
        # Use a known now_utc so "today" is deterministic
        now_utc = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        today = date(2024, 6, 15)

        task = generate_daily_task(db, user.id, today)
        result = get_current_task(db, user.id, now_utc=now_utc)

        assert result is not None
        assert result.task.id == task.id
        # At 10:00 UTC, end of day is 23:59:59 => ~13.99 hours remaining
        assert result.hours_remaining > 13.0
        assert result.hours_remaining < 14.0
        db.close()

    def test_returns_none_when_no_task_exists(self):
        """Should return None when no task exists for today."""
        db = _create_test_session()
        user = _create_user(db)
        now_utc = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        result = get_current_task(db, user.id, now_utc=now_utc)

        assert result is None
        db.close()

    def test_returns_none_for_nonexistent_user(self):
        """Should return None for nonexistent user."""
        db = _create_test_session()

        result = get_current_task(db, 9999, now_utc=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc))

        assert result is None
        db.close()

    def test_hours_remaining_near_end_of_day(self):
        """Should return small hours remaining near end of day."""
        db = _create_test_session()
        user = _create_user(db)
        now_utc = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        today = date(2024, 6, 15)

        generate_daily_task(db, user.id, today)
        result = get_current_task(db, user.id, now_utc=now_utc)

        assert result is not None
        # At 23:00, end of day is 23:59:59 => ~0.99 hours remaining
        assert result.hours_remaining > 0.9
        assert result.hours_remaining < 1.0
        db.close()

    def test_hours_remaining_never_negative(self):
        """Hours remaining should not be negative even past end of day."""
        db = _create_test_session()
        user = _create_user(db)
        # Simulate being at 23:59:59 on that day
        now_utc = datetime(2024, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
        today = date(2024, 6, 15)

        generate_daily_task(db, user.id, today)
        result = get_current_task(db, user.id, now_utc=now_utc)

        assert result is not None
        assert result.hours_remaining >= 0.0
        db.close()


class TestCheckGracePeriod:
    """Tests for check_grace_period."""

    def test_no_grace_period_when_no_yesterday_task(self):
        """Should return inactive when there's no task for yesterday."""
        db = _create_test_session()
        user = _create_user(db)
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        result = check_grace_period(db, user.id, now_utc=now_utc)

        assert result.is_active is False
        db.close()

    def test_grace_period_active_for_pending_yesterday_task(self):
        """Should activate grace period when yesterday's task is pending."""
        db = _create_test_session()
        user = _create_user(db)
        yesterday = date(2024, 6, 15)
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        generate_daily_task(db, user.id, yesterday)
        result = check_grace_period(db, user.id, now_utc=now_utc)

        assert result.is_active is True
        assert result.task is not None
        assert result.task.status == DailyTaskStatus.grace_period
        assert result.remaining_hours > 0
        db.close()

    def test_grace_period_transitions_pending_to_grace_period(self):
        """Should transition yesterday's pending task to grace_period status."""
        db = _create_test_session()
        user = _create_user(db)
        yesterday = date(2024, 6, 15)
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        task = generate_daily_task(db, user.id, yesterday)
        assert task.status == DailyTaskStatus.pending

        check_grace_period(db, user.id, now_utc=now_utc)

        db.refresh(task)
        assert task.status == DailyTaskStatus.grace_period
        db.close()

    def test_grace_period_remaining_time_calculation(self):
        """Should calculate remaining hours and minutes correctly."""
        db = _create_test_session()
        user = _create_user(db)
        yesterday = date(2024, 6, 15)
        # At 10:00 on the 16th, grace deadline is 23:59:59 on the 16th
        # So ~13.99 hours remain
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        generate_daily_task(db, user.id, yesterday)
        result = check_grace_period(db, user.id, now_utc=now_utc)

        assert result.is_active is True
        assert result.remaining_hours > 13.0
        assert result.remaining_hours < 14.0
        db.close()

    def test_grace_period_expired_marks_missed(self):
        """Should mark task as missed when grace period has expired."""
        db = _create_test_session()
        user = _create_user(db)
        user.current_streak = 5
        db.commit()

        yesterday = date(2024, 6, 15)
        # Grace period for yesterday's task expires at end of today (June 16)
        # Use a time after that
        now_utc = datetime(2024, 6, 17, 0, 0, 1, tzinfo=timezone.utc)

        task = generate_daily_task(db, user.id, yesterday)

        # We need to check grace period on June 17, making yesterday = June 16
        # and our pending task is from June 15 (before yesterday), so it gets missed
        # as a multi-day miss. Let's adjust to test correctly.
        # Actually, on June 17 at 00:00:01 UTC, today = June 17, yesterday = June 16.
        # The task from June 15 is "older than yesterday" so it's a multi-day miss.
        result = check_grace_period(db, user.id, now_utc=now_utc)

        assert result.is_active is False
        db.refresh(user)
        assert user.current_streak == 0
        db.refresh(task)
        assert task.status == DailyTaskStatus.missed
        db.close()

    def test_no_grace_period_when_yesterday_task_completed(self):
        """Should return inactive when yesterday's task is already completed."""
        db = _create_test_session()
        user = _create_user(db)
        yesterday = date(2024, 6, 15)
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        task = generate_daily_task(db, user.id, yesterday)
        complete_task(db, task.id, "no_transactions")

        result = check_grace_period(db, user.id, now_utc=now_utc)

        assert result.is_active is False
        db.close()

    def test_multi_day_miss_resets_streak(self):
        """Should reset streak when older tasks are found pending."""
        db = _create_test_session()
        user = _create_user(db)
        user.current_streak = 10
        db.commit()

        # Create tasks for 3 days ago and 2 days ago (both missed)
        two_days_ago = date(2024, 6, 14)
        three_days_ago = date(2024, 6, 13)
        yesterday = date(2024, 6, 15)
        now_utc = datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc)

        generate_daily_task(db, user.id, three_days_ago)
        generate_daily_task(db, user.id, two_days_ago)
        generate_daily_task(db, user.id, yesterday)

        result = check_grace_period(db, user.id, now_utc=now_utc)

        # Yesterday's task enters grace period, but older ones are marked missed
        db.refresh(user)
        assert user.current_streak == 0  # Reset due to multi-day miss
        # The grace period should still be active for yesterday
        assert result.is_active is True
        db.close()

    def test_returns_inactive_for_nonexistent_user(self):
        """Should return inactive for nonexistent user."""
        db = _create_test_session()

        result = check_grace_period(db, 9999, now_utc=datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc))

        assert result.is_active is False
        db.close()


class TestAutoCompleteOnTransaction:
    """Tests for auto_complete_on_transaction."""

    def test_auto_completes_pending_task(self):
        """Should auto-complete pending task when transaction is logged."""
        db = _create_test_session()
        user = _create_user(db)
        today = date(2024, 6, 15)

        generate_daily_task(db, user.id, today)
        result = auto_complete_on_transaction(db, user.id, today)

        assert result is not None
        assert result.status == DailyTaskStatus.completed
        assert result.completion_type == DailyTaskCompletionType.transaction_logged

        db.refresh(user)
        assert user.current_streak == 1
        db.close()

    def test_auto_completes_grace_period_task(self):
        """Should auto-complete grace_period task when transaction is logged."""
        db = _create_test_session()
        user = _create_user(db)
        task_date = date(2024, 6, 15)

        task = generate_daily_task(db, user.id, task_date)
        task.status = DailyTaskStatus.grace_period
        db.commit()

        result = auto_complete_on_transaction(db, user.id, task_date)

        assert result is not None
        assert result.status == DailyTaskStatus.completed
        assert result.completion_type == DailyTaskCompletionType.transaction_logged
        db.close()

    def test_does_not_complete_already_completed_task(self):
        """Should return None when task is already completed."""
        db = _create_test_session()
        user = _create_user(db)
        today = date(2024, 6, 15)

        task = generate_daily_task(db, user.id, today)
        complete_task(db, task.id, "no_transactions")

        result = auto_complete_on_transaction(db, user.id, today)

        assert result is None
        db.close()

    def test_does_not_complete_missed_task(self):
        """Should return None when task is already missed."""
        db = _create_test_session()
        user = _create_user(db)
        today = date(2024, 6, 15)

        task = generate_daily_task(db, user.id, today)
        task.status = DailyTaskStatus.missed
        db.commit()

        result = auto_complete_on_transaction(db, user.id, today)

        assert result is None
        db.close()

    def test_returns_none_when_no_task_exists(self):
        """Should return None when no task exists for the date."""
        db = _create_test_session()
        user = _create_user(db)

        result = auto_complete_on_transaction(db, user.id, date(2024, 6, 15))

        assert result is None
        db.close()

    def test_does_not_double_increment_streak(self):
        """Calling auto_complete twice should not increment streak again."""
        db = _create_test_session()
        user = _create_user(db)
        today = date(2024, 6, 15)

        generate_daily_task(db, user.id, today)

        # First call completes it
        auto_complete_on_transaction(db, user.id, today)
        db.refresh(user)
        assert user.current_streak == 1

        # Second call should return None (already completed)
        result = auto_complete_on_transaction(db, user.id, today)
        assert result is None
        db.refresh(user)
        assert user.current_streak == 1
        db.close()
