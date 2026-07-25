"""Notification service for in-app notification management.

Handles creation, retrieval, and marking notifications as read.
Also provides daily reminder logic with at-most-once enforcement.
Integrates with push delivery service for dual in-app + push notifications.

Requirements:
- 12.1: Support both in-app and push notifications for all event types
- 12.2: Send reminder when user hasn't completed daily task by configured time
         (default 8 PM local), at most once per day
- 12.3: Allow user to enable/disable push independently of in-app
- 12.4: Both notifications enabled by default
- 12.5: Fall back to in-app only when push permission denied
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.notification import Notification
from app.services.push_service import PUSH_NOTIFICATION_TYPES, send_push_notification

logger = logging.getLogger(__name__)

# Valid notification types
NOTIFICATION_TYPES = (
    "daily_reminder",
    "budget_80",
    "budget_100",
    "spike_alert",
    "weekly_summary",
    "monthly_summary",
    "summary_ready",
    "ai_coaching",
)

# Mapping from notification types to their push equivalent type
# (some in-app types map to the same push type for simplicity)
_PUSH_TYPE_MAP = {
    "daily_reminder": "daily_reminder",
    "budget_80": "budget_80",
    "budget_100": "budget_100",
    "spike_alert": "spike_alert",
    "weekly_summary": "summary_ready",
    "monthly_summary": "summary_ready",
    "summary_ready": "summary_ready",
    "ai_coaching": "ai_coaching",
}


def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    body: str,
    payload: dict | None = None,
    send_push: bool = True,
    push_url: Optional[str] = None,
) -> Notification:
    """Create an in-app notification for a user and optionally send a push notification.

    Args:
        db: Database session.
        user_id: ID of the user to notify.
        notification_type: One of the valid NOTIFICATION_TYPES.
        title: Short notification title.
        body: Notification body text.
        payload: Optional JSON-serializable dict with extra data.
        send_push: Whether to also attempt push delivery (default True).
                   Set to False to create in-app only (e.g., when push disabled by user).
        push_url: Optional action URL for the push notification click handler.

    Returns:
        The created Notification record.
    """
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        payload_json=json.dumps(payload) if payload else None,
        is_read=False,
    )
    db.add(notification)
    db.flush()

    # Attempt push delivery alongside in-app
    if send_push:
        push_type = _PUSH_TYPE_MAP.get(notification_type)
        if push_type and push_type in PUSH_NOTIFICATION_TYPES:
            # Build context for tag generation from the payload
            context = None
            if payload:
                context = {}
                if "task_date" in payload:
                    context["date"] = payload["task_date"]
                if "budget_id" in payload:
                    context["budget_id"] = payload["budget_id"]
                if "category_id" in payload:
                    context["category_id"] = payload["category_id"]

            push_sent = send_push_notification(
                db=db,
                user_id=user_id,
                notification_type=push_type,
                title=title,
                body=body,
                url=push_url,
                context=context if context else None,
            )
            if not push_sent:
                logger.debug(
                    f"Push not sent for user {user_id} (type={notification_type}). "
                    "Falling back to in-app only."
                )

    return notification


def get_unread_notifications(db: Session, user_id: int) -> list[Notification]:
    """Get all unread in-app notifications for a user, ordered newest first.

    Args:
        db: Database session.
        user_id: ID of the user.

    Returns:
        List of unread Notification records.
    """
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .order_by(Notification.created_at_utc.desc())
        .all()
    )


def mark_as_read(db: Session, notification_id: int, user_id: int) -> Notification | None:
    """Mark a notification as read.

    Args:
        db: Database session.
        notification_id: ID of the notification to mark.
        user_id: ID of the owning user (for authorization).

    Returns:
        The updated Notification, or None if not found or not owned by user.
    """
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        .first()
    )
    if notification is None:
        return None

    notification.is_read = True
    db.flush()
    return notification


def send_daily_reminder(db: Session, user_id: int, task_date: date) -> Notification | None:
    """Send a daily task reminder notification with at-most-once enforcement.

    Checks that:
    1. The daily task for the given date is still incomplete (pending or grace_period).
    2. No daily_reminder notification has been sent for this user today.

    If both conditions are met, creates and returns a reminder notification.
    Otherwise, returns None (no duplicate sent).

    Args:
        db: Database session.
        user_id: ID of the user to remind.
        task_date: The date of the daily task to check.

    Returns:
        The created Notification if reminder was sent, None otherwise.

    Requirement 12.2: At most one reminder per day per user.
    """
    # Check if the daily task is still incomplete
    daily_task = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == task_date,
        )
        .first()
    )

    if daily_task is None:
        # No task for this date — nothing to remind about
        return None

    if daily_task.status not in ("pending", "grace_period"):
        # Task already completed or missed — no reminder needed
        return None

    # Enforce at-most-one reminder per day: check if a daily_reminder was already sent
    # for this specific task_date by looking at the payload_json field.
    task_date_str = task_date.isoformat()
    existing_reminder = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.notification_type == "daily_reminder",
            Notification.payload_json.contains(task_date_str),
        )
        .first()
    )

    if existing_reminder is not None:
        # Already sent a reminder today — enforce at-most-once
        return None

    # Create the reminder notification
    notification = create_notification(
        db=db,
        user_id=user_id,
        notification_type="daily_reminder",
        title="Don't forget to log today!",
        body="You haven't logged any transactions today. Tap to log now and keep your streak going.",
        payload={"task_date": task_date.isoformat()},
    )

    return notification
