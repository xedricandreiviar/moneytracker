"""Pydantic schemas for notification API endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Response schema for a single notification."""

    id: int
    user_id: int
    notification_type: str
    title: str
    body: str
    payload: Optional[dict[str, Any]] = None
    is_read: bool
    created_at_utc: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """Response schema for GET /api/notifications (unread list)."""

    notifications: list[NotificationResponse]
    count: int


class NotificationReadResponse(BaseModel):
    """Response schema for PUT /api/notifications/{id}/read."""

    id: int
    is_read: bool
    message: str = "Notification marked as read."


# --- Push Subscription Schemas ---


class PushSubscriptionKeys(BaseModel):
    """Keys from the browser PushSubscription object."""

    p256dh: str = Field(..., description="Client public key (base64url)")
    auth: str = Field(..., description="Authentication secret (base64url)")


class PushSubscriptionRequest(BaseModel):
    """Request schema for POST /api/notifications/push-subscription.

    Mirrors the browser PushSubscription JSON structure.
    """

    endpoint: str = Field(..., description="Push service endpoint URL")
    keys: PushSubscriptionKeys


class PushSubscriptionResponse(BaseModel):
    """Response schema after registering a push subscription."""

    id: int
    user_id: int
    endpoint: str
    created_at_utc: datetime
    message: str = "Push subscription registered successfully."

    model_config = {"from_attributes": True}
