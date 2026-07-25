"""StreakService for managing user daily logging streaks.

Handles streak increment (with optimistic locking), reset, and evaluation
of missed days including grace period logic.

Requirements covered: 1.6, 2.1, 2.2, 2.3, 2.5
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask, DailyTaskStatus
from app.models.user import User

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """Raised when optimistic locking detects a concurrent modification."""

    pass


@dataclass
class StreakEvaluation:
    """Result of evaluating missed days and grace period status."""

    current_streak: int
    grace_period_active: bool
    grace_remaining_seconds: Optional[float] = None
    days_missed: int = 0


def get_current_streak(db: Session, user_id: int) -> int:
    """Read the current streak count for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        Current streak count (0 if user not found).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return 0
    return user.current_streak


def increment_streak(db: Session, user_id: int) -> int:
    """Increment the user's streak by one using optimistic locking.

    Uses the version column to prevent race conditions. If the version
    has changed since the read, raises OptimisticLockError.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        The new streak count after incrementing.

    Raises:
        OptimisticLockError: If concurrent modification detected.
        ValueError: If user not found.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    current_version = user.version
    new_streak = user.current_streak + 1
    now_utc = datetime.now(timezone.utc)

    # Attempt update with optimistic locking
    rows_updated = (
        db.query(User)
        .filter(User.id == user_id, User.version == current_version)
        .update(
            {
                User.current_streak: new_streak,
                User.streak_last_updated_utc: now_utc,
                User.version: current_version + 1,
            },
            synchronize_session="fetch",
        )
    )

    if rows_updated == 0:
        db.rollback()
        raise OptimisticLockError(
            f"Concurrent modification detected for user {user_id}. "
            f"Expected version {current_version}."
        )

    db.commit()
    db.refresh(user)
    return user.current_streak


def reset_streak(db: Session, user_id: int) -> int:
    """Reset the user's streak to zero.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        0 (the reset streak value).

    Raises:
        ValueError: If user not found.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    user.current_streak = 0
    user.streak_last_updated_utc = datetime.now(timezone.utc)
    user.version += 1
    db.commit()
    db.refresh(user)
    return 0


def _get_user_local_today(user: User, now_utc: Optional[datetime] = None) -> date:
    """Get the current local date for the user based on their timezone.

    Args:
        user: The User instance.
        now_utc: Optional override for current UTC time (for testing).

    Returns:
        The user's local date.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    try:
        user_tz = ZoneInfo(user.timezone)
        return now_utc.astimezone(user_tz).date()
    except (KeyError, Exception):
        return now_utc.date()


def _get_grace_period_end(missed_date: date, user_tz: ZoneInfo) -> datetime:
    """Calculate the grace period end time for a missed day.

    The grace period is a 24-hour window: it ends at 23:59:59 of the day
    following the missed day (in the user's local timezone).

    Args:
        missed_date: The date that was missed.
        user_tz: The user's timezone.

    Returns:
        The UTC datetime when the grace period expires.
    """
    # Grace period ends at end of the next day after the missed date
    grace_end_local = datetime.combine(
        missed_date + timedelta(days=1),
        time(23, 59, 59),
        tzinfo=user_tz,
    )
    return grace_end_local.astimezone(timezone.utc)


def evaluate_missed_days(
    db: Session,
    user_id: int,
    now_utc: Optional[datetime] = None,
) -> StreakEvaluation:
    """Evaluate missed days and grace period status for a user.

    Logic:
    1. Check for pending tasks older than yesterday — mark as missed, reset streak.
    2. Check yesterday's task:
       - If pending and grace period not expired → mark as grace_period.
       - If pending and grace period expired → mark as missed, reset streak.
    3. Only the most recent missed day (yesterday) is recoverable via grace period.

    Args:
        db: Database session.
        user_id: The user's ID.
        now_utc: Optional override for current UTC time (for testing).

    Returns:
        StreakEvaluation with current state.

    Raises:
        ValueError: If user not found.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    try:
        user_tz = ZoneInfo(user.timezone)
    except (KeyError, Exception):
        user_tz = ZoneInfo("UTC")

    today = now_utc.astimezone(user_tz).date()
    yesterday = today - timedelta(days=1)

    streak_was_reset = False
    days_missed = 0

    # Step 1: Check for tasks older than yesterday that are still pending
    # These are beyond recovery — mark as missed and reset streak
    older_pending_tasks = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date < yesterday,
            DailyTask.status.in_([
                DailyTaskStatus.pending,
                DailyTaskStatus.grace_period,
            ]),
        )
        .all()
    )

    if older_pending_tasks:
        for task in older_pending_tasks:
            task.status = DailyTaskStatus.missed
            days_missed += 1
        # Requirement 2.5: Multiple missed days → reset streak
        user.current_streak = 0
        user.streak_last_updated_utc = now_utc
        user.version += 1
        streak_was_reset = True

    # Step 2: Check yesterday's task
    yesterday_task = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == yesterday,
        )
        .first()
    )

    grace_period_active = False
    grace_remaining_seconds = None

    if yesterday_task and yesterday_task.status in (
        DailyTaskStatus.pending,
        DailyTaskStatus.grace_period,
    ):
        grace_end_utc = _get_grace_period_end(yesterday, user_tz)

        if now_utc <= grace_end_utc:
            # Grace period still active — mark as grace_period
            yesterday_task.status = DailyTaskStatus.grace_period
            grace_period_active = True
            grace_remaining_seconds = (grace_end_utc - now_utc).total_seconds()
        else:
            # Grace period expired — mark as missed, reset streak
            yesterday_task.status = DailyTaskStatus.missed
            days_missed += 1
            if not streak_was_reset:
                # Requirement 2.3: Grace period expired → reset streak
                user.current_streak = 0
                user.streak_last_updated_utc = now_utc
                user.version += 1
                streak_was_reset = True

    db.commit()
    db.refresh(user)

    return StreakEvaluation(
        current_streak=user.current_streak,
        grace_period_active=grace_period_active,
        grace_remaining_seconds=grace_remaining_seconds,
        days_missed=days_missed,
    )
