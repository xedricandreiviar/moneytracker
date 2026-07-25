"""DailyTaskService for managing daily logging tasks and habit tracking.

Handles daily task generation, completion (via transaction or "no transactions"),
grace period evaluation, and streak increment on task completion.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask, DailyTaskCompletionType, DailyTaskStatus
from app.models.user import User

logger = logging.getLogger(__name__)


class DailyTaskError(Exception):
    """Base error for daily task operations."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class GracePeriodStatus:
    """Status of the grace period for a user's missed day."""

    is_active: bool
    task: Optional[DailyTask] = None
    remaining_hours: float = 0.0
    remaining_minutes: float = 0.0


@dataclass
class CurrentTaskInfo:
    """Information about the user's current daily task."""

    task: DailyTask
    hours_remaining: float


def _get_user_local_today(user: User, now_utc: Optional[datetime] = None) -> date:
    """Get the current local date for a user based on their timezone.

    Args:
        user: The user whose timezone to use.
        now_utc: Optional UTC datetime (defaults to current time).

    Returns:
        The local date in the user's timezone.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    try:
        from zoneinfo import ZoneInfo

        user_tz = ZoneInfo(user.timezone)
        local_now = now_utc.astimezone(user_tz)
        return local_now.date()
    except (KeyError, ImportError):
        return now_utc.date()


def _get_user_timezone(user: User):
    """Get the ZoneInfo for a user's timezone with UTC fallback.

    Args:
        user: The user whose timezone to resolve.

    Returns:
        A ZoneInfo (or timezone.utc fallback).
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(user.timezone)
    except (KeyError, ImportError):
        return timezone.utc


def generate_daily_task(
    db: Session,
    user_id: int,
    task_date: date,
    now_utc: Optional[datetime] = None,
) -> DailyTask:
    """Create a new pending daily task for the specified date.

    If a task already exists for this user+date, returns the existing task
    without creating a duplicate (idempotent).

    Args:
        db: Database session.
        user_id: The user's ID.
        task_date: The date for the new task.
        now_utc: Optional UTC datetime for created_at (defaults to current time).

    Returns:
        The created (or existing) DailyTask.

    Raises:
        DailyTaskError: If the user does not exist.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise DailyTaskError(f"User {user_id} not found.")

    # Check for existing task (idempotent)
    existing = (
        db.query(DailyTask)
        .filter(DailyTask.user_id == user_id, DailyTask.task_date == task_date)
        .first()
    )
    if existing is not None:
        return existing

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    task = DailyTask(
        user_id=user_id,
        task_date=task_date,
        status=DailyTaskStatus.pending,
        completion_type=None,
        completed_at_utc=None,
        created_at_utc=now_utc,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    logger.info(f"Generated daily task for user {user_id} on {task_date}")
    return task


def complete_task(
    db: Session,
    task_id: int,
    completion_type: str,
    now_utc: Optional[datetime] = None,
) -> DailyTask:
    """Transition a pending or grace_period task to completed.

    Also increments the user's streak by 1 on successful completion.

    Args:
        db: Database session.
        task_id: The daily task ID to complete.
        completion_type: One of "transaction_logged", "no_transactions", "grace_recovery".
        now_utc: Optional UTC datetime for completed_at (defaults to current time).

    Returns:
        The updated DailyTask.

    Raises:
        DailyTaskError: If the task is not found, already completed/missed, or
            the completion_type is invalid.
    """
    task = db.query(DailyTask).filter(DailyTask.id == task_id).first()
    if task is None:
        raise DailyTaskError(f"DailyTask {task_id} not found.")

    # Validate completion_type
    valid_types = {ct.value for ct in DailyTaskCompletionType}
    if completion_type not in valid_types:
        raise DailyTaskError(
            f"Invalid completion_type '{completion_type}'. "
            f"Must be one of: {', '.join(valid_types)}"
        )

    # Only pending or grace_period tasks can be completed
    if task.status not in (DailyTaskStatus.pending, DailyTaskStatus.grace_period):
        raise DailyTaskError(
            f"Cannot complete task with status '{task.status.value}'. "
            f"Only 'pending' or 'grace_period' tasks can be completed."
        )

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # Transition to completed
    task.status = DailyTaskStatus.completed
    task.completion_type = DailyTaskCompletionType(completion_type)
    task.completed_at_utc = now_utc

    # Increment user's streak (Requirement 1.6)
    user = db.query(User).filter(User.id == task.user_id).first()
    if user is not None:
        user.current_streak += 1
        user.streak_last_updated_utc = now_utc

    db.commit()
    db.refresh(task)

    logger.info(
        f"Completed task {task_id} for user {task.user_id} "
        f"via '{completion_type}', streak now {user.current_streak if user else 'unknown'}"
    )
    return task


def get_current_task(
    db: Session,
    user_id: int,
    now_utc: Optional[datetime] = None,
) -> Optional[CurrentTaskInfo]:
    """Return today's task for the user with hours remaining in the day.

    Args:
        db: Database session.
        user_id: The user's ID.
        now_utc: Optional UTC datetime (defaults to current time).

    Returns:
        CurrentTaskInfo with the task and hours remaining, or None if no task
        exists for today.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    today = _get_user_local_today(user, now_utc)

    task = (
        db.query(DailyTask)
        .filter(DailyTask.user_id == user_id, DailyTask.task_date == today)
        .first()
    )

    if task is None:
        return None

    # Calculate hours remaining in the user's current day
    user_tz = _get_user_timezone(user)
    local_now = now_utc.astimezone(user_tz)
    end_of_day = datetime.combine(today, time(23, 59, 59), tzinfo=user_tz)
    remaining = end_of_day - local_now
    hours_remaining = max(0.0, remaining.total_seconds() / 3600)

    return CurrentTaskInfo(task=task, hours_remaining=hours_remaining)


def check_grace_period(
    db: Session,
    user_id: int,
    now_utc: Optional[datetime] = None,
) -> GracePeriodStatus:
    """Evaluate yesterday's task and compute grace period remaining time.

    If yesterday's task is still pending:
    - If the grace period (all of today) hasn't expired, transition to grace_period
      and return active status with remaining time.
    - If the grace period has expired (after end of today), mark as missed and
      reset the user's streak.

    Also checks for older pending tasks (multi-day misses) and marks them as missed.

    Args:
        db: Database session.
        user_id: The user's ID.
        now_utc: Optional UTC datetime (defaults to current time).

    Returns:
        GracePeriodStatus indicating whether a grace period is active and
        remaining time.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return GracePeriodStatus(is_active=False)

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    user_tz = _get_user_timezone(user)
    today = _get_user_local_today(user, now_utc)
    yesterday = today - timedelta(days=1)

    # Handle multi-day misses: mark any pending tasks older than yesterday as missed
    older_pending_tasks = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date < yesterday,
            DailyTask.status.in_([DailyTaskStatus.pending, DailyTaskStatus.grace_period]),
        )
        .all()
    )

    if older_pending_tasks:
        for old_task in older_pending_tasks:
            old_task.status = DailyTaskStatus.missed
        user.current_streak = 0
        user.streak_last_updated_utc = now_utc
        db.commit()

    # Check yesterday's task
    yesterday_task = (
        db.query(DailyTask)
        .filter(DailyTask.user_id == user_id, DailyTask.task_date == yesterday)
        .first()
    )

    if yesterday_task is None:
        return GracePeriodStatus(is_active=False)

    # If already completed or missed, no grace period needed
    if yesterday_task.status in (DailyTaskStatus.completed, DailyTaskStatus.missed):
        return GracePeriodStatus(is_active=False)

    # Yesterday's task is pending or grace_period — evaluate grace window
    # Grace period = all of today (00:00:00 to 23:59:59 in user's timezone)
    local_now = now_utc.astimezone(user_tz)
    grace_deadline = datetime.combine(today, time(23, 59, 59), tzinfo=user_tz)

    if local_now > grace_deadline:
        # Grace period expired — mark as missed, reset streak
        yesterday_task.status = DailyTaskStatus.missed
        user.current_streak = 0
        user.streak_last_updated_utc = now_utc
        db.commit()
        return GracePeriodStatus(is_active=False)

    # Grace period is active — transition to grace_period if still pending
    if yesterday_task.status == DailyTaskStatus.pending:
        yesterday_task.status = DailyTaskStatus.grace_period
        db.commit()
        db.refresh(yesterday_task)

    # Calculate remaining time
    remaining = grace_deadline - local_now
    remaining_seconds = max(0.0, remaining.total_seconds())
    remaining_hours = remaining_seconds / 3600
    remaining_minutes = (remaining_seconds % 3600) / 60

    return GracePeriodStatus(
        is_active=True,
        task=yesterday_task,
        remaining_hours=remaining_hours,
        remaining_minutes=remaining_minutes,
    )


def auto_complete_on_transaction(
    db: Session,
    user_id: int,
    transaction_date_local: date,
    now_utc: Optional[datetime] = None,
) -> Optional[DailyTask]:
    """Auto-complete the daily task when a transaction is logged for the current day.

    Finds the task for the given date and, if it's in pending or grace_period
    status, marks it completed with completion_type="transaction_logged".

    Args:
        db: Database session.
        user_id: The user's ID.
        transaction_date_local: The local date of the transaction.
        now_utc: Optional UTC datetime (defaults to current time).

    Returns:
        The completed DailyTask if one was found and completed, or None.
    """
    task = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == transaction_date_local,
        )
        .first()
    )

    if task is None:
        return None

    # Only auto-complete if pending or in grace period
    if task.status not in (DailyTaskStatus.pending, DailyTaskStatus.grace_period):
        return None

    # Use complete_task to handle the completion + streak increment
    return complete_task(
        db=db,
        task_id=task.id,
        completion_type=DailyTaskCompletionType.transaction_logged.value,
        now_utc=now_utc,
    )
