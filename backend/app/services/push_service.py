"""Push notification delivery service using pywebpush.

Handles sending Web Push notifications to registered subscriptions.
Uses VAPID keys from environment configuration.
Falls back to in-app only when push delivery fails or permission is denied.

Requirements:
- 12.1: Support push notifications for all event types
- 12.3: Allow enable/disable push independently of in-app
- 12.4: Both enabled by default
- 12.5: Fall back to in-app when push permission denied
"""

import json
import logging
from datetime import date
from typing import Optional

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.config import settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)

# Notification types that support push delivery
PUSH_NOTIFICATION_TYPES = (
    "daily_reminder",
    "budget_80",
    "budget_100",
    "spike_alert",
    "summary_ready",
    "ai_coaching",
)


def _generate_tag(notification_type: str, context: Optional[dict] = None) -> str:
    """Generate a notification tag to prevent duplicates of the same type.

    Tags are used by the browser to replace existing notifications of the same type
    rather than stacking duplicates.

    Args:
        notification_type: The type of notification (e.g., "daily_reminder").
        context: Optional dict with extra context (e.g., {"date": "2024-01-15"}).

    Returns:
        A tag string like "daily_reminder_2024-01-15" or "budget_80_5".
    """
    if context:
        if "date" in context:
            return f"{notification_type}_{context['date']}"
        if "budget_id" in context:
            return f"{notification_type}_{context['budget_id']}"
        if "category_id" in context:
            return f"{notification_type}_{context['category_id']}"
    # Default tag: just the notification type (prevents stacking of same type)
    return notification_type


def register_push_subscription(
    db: Session, user_id: int, endpoint: str, p256dh: str, auth: str
) -> PushSubscription:
    """Register a new VAPID push subscription for a user.

    If an identical endpoint already exists for this user, update the keys
    rather than creating a duplicate.

    Args:
        db: Database session.
        user_id: ID of the user.
        endpoint: The push service endpoint URL.
        p256dh: The client public key (base64url-encoded).
        auth: The authentication secret (base64url-encoded).

    Returns:
        The created or updated PushSubscription record.
    """
    # Check if this endpoint is already registered for the user
    existing = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
        .first()
    )

    if existing:
        # Update keys in case they changed (subscription refresh)
        existing.p256dh = p256dh
        existing.auth = auth
        db.flush()
        return existing

    # Create new subscription
    subscription = PushSubscription(
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
    )
    db.add(subscription)
    db.flush()
    return subscription


def get_user_push_subscriptions(db: Session, user_id: int) -> list[PushSubscription]:
    """Get all active push subscriptions for a user.

    Args:
        db: Database session.
        user_id: ID of the user.

    Returns:
        List of PushSubscription records.
    """
    return (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user_id)
        .all()
    )


def send_push_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    body: str,
    url: Optional[str] = None,
    context: Optional[dict] = None,
) -> bool:
    """Send a push notification to all of a user's registered subscriptions.

    Uses the notification tag to prevent duplicate push notifications of the
    same type on the client device.

    Falls back gracefully when:
    - No push subscriptions exist (user never granted permission)
    - VAPID keys are not configured
    - Push delivery fails (expired subscription, network error)

    Args:
        db: Database session.
        user_id: ID of the user to notify.
        notification_type: One of PUSH_NOTIFICATION_TYPES.
        title: Notification title.
        body: Notification body text.
        url: Optional action URL to open when notification is clicked.
        context: Optional dict for tag generation (e.g., {"date": "2024-01-15"}).

    Returns:
        True if at least one push was delivered successfully, False otherwise.
    """
    if notification_type not in PUSH_NOTIFICATION_TYPES:
        logger.warning(
            f"Notification type '{notification_type}' not supported for push delivery."
        )
        return False

    # Check VAPID configuration
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.warning("VAPID keys not configured. Falling back to in-app only.")
        return False

    # Get user's push subscriptions
    subscriptions = get_user_push_subscriptions(db, user_id)
    if not subscriptions:
        # No subscriptions = user never granted push permission or hasn't subscribed
        # Fall back to in-app only (Requirement 12.5)
        logger.debug(
            f"No push subscriptions for user {user_id}. In-app notification only."
        )
        return False

    tag = _generate_tag(notification_type, context)

    # Build push payload
    payload = json.dumps({
        "title": title,
        "body": body,
        "tag": tag,
        "notification_type": notification_type,
        "url": url or "/",
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/badge-72x72.png",
    })

    vapid_claims = {
        "sub": settings.vapid_claims_email,
    }

    any_success = False
    expired_subscription_ids = []

    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=vapid_claims,
            )
            any_success = True
            logger.info(
                f"Push notification sent to user {user_id} "
                f"(type={notification_type}, tag={tag})"
            )
        except WebPushException as e:
            # HTTP 410 Gone or 404 means subscription is expired/invalid
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
                if status_code in (404, 410):
                    expired_subscription_ids.append(subscription.id)
                    logger.info(
                        f"Removing expired push subscription {subscription.id} "
                        f"for user {user_id} (HTTP {status_code})"
                    )
                else:
                    logger.error(
                        f"Push delivery failed for user {user_id}, "
                        f"subscription {subscription.id}: HTTP {status_code} - {e}"
                    )
            else:
                logger.error(
                    f"Push delivery failed for user {user_id}, "
                    f"subscription {subscription.id}: {e}"
                )
        except Exception as e:
            logger.error(
                f"Unexpected error sending push to user {user_id}, "
                f"subscription {subscription.id}: {e}"
            )

    # Clean up expired subscriptions
    if expired_subscription_ids:
        db.query(PushSubscription).filter(
            PushSubscription.id.in_(expired_subscription_ids)
        ).delete(synchronize_session="fetch")
        db.flush()

    return any_success
