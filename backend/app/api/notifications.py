"""API endpoints for notification management.

Provides:
- GET /api/notifications — list unread in-app notifications
- PUT /api/notifications/{id}/read — mark a notification as read
- POST /api/notifications/push-subscription — register VAPID push subscription

Requirements:
- 12.1: Support in-app and push notifications
- 12.3: Allow user to enable/disable push independently of in-app
- 12.4: Both notifications enabled by default
- 12.5: Fall back to in-app when push permission denied
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationReadResponse,
    NotificationResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
)
from app.services.notification_service import get_unread_notifications, mark_as_read
from app.services.push_service import register_push_subscription

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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


def _notification_to_response(notification) -> NotificationResponse:
    """Convert a Notification model to response schema."""
    payload = None
    if notification.payload_json:
        try:
            payload = json.loads(notification.payload_json)
        except (json.JSONDecodeError, TypeError):
            payload = None

    return NotificationResponse(
        id=notification.id,
        user_id=notification.user_id,
        notification_type=notification.notification_type,
        title=notification.title,
        body=notification.body,
        payload=payload,
        is_read=notification.is_read,
        created_at_utc=notification.created_at_utc,
    )


@router.get("", response_model=NotificationListResponse)
def list_unread_notifications(
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    """Get all unread in-app notifications for the current user.

    Returns notifications ordered by most recent first.
    """
    notifications = get_unread_notifications(db=db, user_id=user.id)
    items = [_notification_to_response(n) for n in notifications]

    return NotificationListResponse(
        notifications=items,
        count=len(items),
    )


@router.put("/{notification_id}/read", response_model=NotificationReadResponse)
def mark_notification_read(
    notification_id: int,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> NotificationReadResponse:
    """Mark a notification as read.

    Returns 404 if the notification does not exist or does not belong to the user.
    """
    notification = mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=user.id,
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found.",
        )

    db.commit()

    return NotificationReadResponse(
        id=notification.id,
        is_read=True,
    )


@router.post("/push-subscription", response_model=PushSubscriptionResponse, status_code=201)
def create_push_subscription(
    subscription: PushSubscriptionRequest,
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
) -> PushSubscriptionResponse:
    """Register a VAPID push subscription for the current user.

    The client should call this after obtaining push permission from the browser
    and receiving the PushSubscription object. If the same endpoint already exists
    for this user, the keys are updated.

    Falls back to in-app notifications only when the user denies push permission
    (i.e., this endpoint is never called).

    Requirements:
    - 12.1: Support push notifications for all event types
    - 12.5: Fall back to in-app when push permission denied (no subscription registered)
    """
    push_sub = register_push_subscription(
        db=db,
        user_id=user.id,
        endpoint=subscription.endpoint,
        p256dh=subscription.keys.p256dh,
        auth=subscription.keys.auth,
    )

    db.commit()

    return PushSubscriptionResponse(
        id=push_sub.id,
        user_id=push_sub.user_id,
        endpoint=push_sub.endpoint,
        created_at_utc=push_sub.created_at_utc,
    )
