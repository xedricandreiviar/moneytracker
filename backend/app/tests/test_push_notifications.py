"""Tests for push notification delivery system.

Tests cover:
- Push subscription registration (POST /api/notifications/push-subscription)
- Push delivery service (send_push_notification)
- Tag generation for duplicate prevention
- Fallback to in-app when no subscriptions exist
- Expired subscription cleanup
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.push_service import (
    PUSH_NOTIFICATION_TYPES,
    _generate_tag,
    get_user_push_subscriptions,
    register_push_subscription,
    send_push_notification,
)
from app.services.notification_service import create_notification


# --- Test Fixtures ---

@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(id=1, timezone="UTC")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client(db_engine):
    """Create a test client with dependency overrides."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Ensure test user exists
    session = TestingSessionLocal()
    user = session.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, timezone="UTC")
        session.add(user)
        session.commit()
    session.close()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# --- Tag Generation Tests ---


class TestTagGeneration:
    """Tests for _generate_tag function."""

    def test_tag_with_date_context(self):
        """Tag includes date when provided in context."""
        tag = _generate_tag("daily_reminder", {"date": "2024-01-15"})
        assert tag == "daily_reminder_2024-01-15"

    def test_tag_with_budget_id_context(self):
        """Tag includes budget_id when provided in context."""
        tag = _generate_tag("budget_80", {"budget_id": 5})
        assert tag == "budget_80_5"

    def test_tag_with_category_id_context(self):
        """Tag includes category_id when provided in context."""
        tag = _generate_tag("spike_alert", {"category_id": 3})
        assert tag == "spike_alert_3"

    def test_tag_without_context(self):
        """Tag defaults to notification type when no context."""
        tag = _generate_tag("ai_coaching")
        assert tag == "ai_coaching"

    def test_tag_without_relevant_context(self):
        """Tag defaults to type when context has no recognized keys."""
        tag = _generate_tag("daily_reminder", {"irrelevant": "value"})
        assert tag == "daily_reminder"


# --- Push Subscription Registration Tests ---


class TestPushSubscriptionRegistration:
    """Tests for register_push_subscription service function."""

    def test_register_new_subscription(self, db_session: Session, test_user: User):
        """Registering a new subscription creates a record."""
        sub = register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/abc123",
            p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XFhYoLvJDZ9h",
            auth="tBHItJI5svbpC7",
        )
        db_session.commit()

        assert sub.id is not None
        assert sub.user_id == test_user.id
        assert sub.endpoint == "https://push.example.com/send/abc123"
        assert sub.p256dh == "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XFhYoLvJDZ9h"
        assert sub.auth == "tBHItJI5svbpC7"
        assert sub.created_at_utc is not None

    def test_register_duplicate_endpoint_updates_keys(self, db_session: Session, test_user: User):
        """Re-registering the same endpoint updates the keys instead of creating duplicate."""
        endpoint = "https://push.example.com/send/abc123"

        # First registration
        sub1 = register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint=endpoint,
            p256dh="old_p256dh_key",
            auth="old_auth_key",
        )
        db_session.commit()
        sub1_id = sub1.id

        # Second registration with same endpoint but new keys
        sub2 = register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint=endpoint,
            p256dh="new_p256dh_key",
            auth="new_auth_key",
        )
        db_session.commit()

        # Should update, not create new
        assert sub2.id == sub1_id
        assert sub2.p256dh == "new_p256dh_key"
        assert sub2.auth == "new_auth_key"

        # Only one record in DB
        count = db_session.query(PushSubscription).filter(
            PushSubscription.user_id == test_user.id
        ).count()
        assert count == 1

    def test_register_multiple_endpoints(self, db_session: Session, test_user: User):
        """A user can have multiple subscriptions (different browsers/devices)."""
        register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/device1",
            p256dh="key1",
            auth="auth1",
        )
        register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/device2",
            p256dh="key2",
            auth="auth2",
        )
        db_session.commit()

        subs = get_user_push_subscriptions(db_session, test_user.id)
        assert len(subs) == 2


# --- Push Delivery Tests ---


class TestPushDelivery:
    """Tests for send_push_notification function."""

    def test_no_subscriptions_returns_false(self, db_session: Session, test_user: User):
        """Returns False (falls back to in-app) when user has no subscriptions."""
        with patch("app.services.push_service.settings") as mock_settings:
            mock_settings.vapid_private_key = "test_private_key"
            mock_settings.vapid_public_key = "test_public_key"
            mock_settings.vapid_claims_email = "mailto:test@example.com"

            result = send_push_notification(
                db=db_session,
                user_id=test_user.id,
                notification_type="daily_reminder",
                title="Test",
                body="Test body",
            )
            assert result is False

    def test_no_vapid_keys_returns_false(self, db_session: Session, test_user: User):
        """Returns False when VAPID keys are not configured."""
        with patch("app.services.push_service.settings") as mock_settings:
            mock_settings.vapid_private_key = ""
            mock_settings.vapid_public_key = ""

            result = send_push_notification(
                db=db_session,
                user_id=test_user.id,
                notification_type="daily_reminder",
                title="Test",
                body="Test body",
            )
            assert result is False

    def test_invalid_notification_type_returns_false(self, db_session: Session, test_user: User):
        """Returns False for unsupported notification types."""
        result = send_push_notification(
            db=db_session,
            user_id=test_user.id,
            notification_type="invalid_type",
            title="Test",
            body="Test body",
        )
        assert result is False

    @patch("app.services.push_service.webpush")
    def test_successful_push_delivery(self, mock_webpush, db_session: Session, test_user: User):
        """Successfully sends push when subscription exists and VAPID configured."""
        # Register a subscription
        register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/abc",
            p256dh="test_p256dh",
            auth="test_auth",
        )
        db_session.commit()

        with patch("app.services.push_service.settings") as mock_settings:
            mock_settings.vapid_private_key = "test_private_key"
            mock_settings.vapid_public_key = "test_public_key"
            mock_settings.vapid_claims_email = "mailto:test@example.com"

            result = send_push_notification(
                db=db_session,
                user_id=test_user.id,
                notification_type="daily_reminder",
                title="Don't forget to log!",
                body="You haven't logged today.",
                context={"date": "2024-01-15"},
            )

        assert result is True
        mock_webpush.assert_called_once()

        # Verify the payload sent to webpush
        call_kwargs = mock_webpush.call_args
        payload = json.loads(call_kwargs.kwargs["data"])
        assert payload["title"] == "Don't forget to log!"
        assert payload["body"] == "You haven't logged today."
        assert payload["tag"] == "daily_reminder_2024-01-15"
        assert payload["notification_type"] == "daily_reminder"

    @patch("app.services.push_service.webpush")
    def test_expired_subscription_cleanup(self, mock_webpush, db_session: Session, test_user: User):
        """Removes expired subscriptions (HTTP 410) and returns False."""
        from pywebpush import WebPushException

        # Register a subscription
        register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/expired",
            p256dh="test_key",
            auth="test_auth",
        )
        db_session.commit()

        # Simulate 410 Gone response
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_webpush.side_effect = WebPushException("Subscription expired", response=mock_response)

        with patch("app.services.push_service.settings") as mock_settings:
            mock_settings.vapid_private_key = "test_private_key"
            mock_settings.vapid_public_key = "test_public_key"
            mock_settings.vapid_claims_email = "mailto:test@example.com"

            result = send_push_notification(
                db=db_session,
                user_id=test_user.id,
                notification_type="budget_80",
                title="Budget Alert",
                body="You've used 80% of your food budget.",
            )

        assert result is False

        # Subscription should be removed
        db_session.commit()
        subs = get_user_push_subscriptions(db_session, test_user.id)
        assert len(subs) == 0

    @patch("app.services.push_service.webpush")
    def test_push_sent_for_all_notification_types(self, mock_webpush, db_session: Session, test_user: User):
        """Verify push can be sent for all supported notification types."""
        register_push_subscription(
            db=db_session,
            user_id=test_user.id,
            endpoint="https://push.example.com/send/abc",
            p256dh="test_p256dh",
            auth="test_auth",
        )
        db_session.commit()

        with patch("app.services.push_service.settings") as mock_settings:
            mock_settings.vapid_private_key = "test_private_key"
            mock_settings.vapid_public_key = "test_public_key"
            mock_settings.vapid_claims_email = "mailto:test@example.com"

            for ntype in PUSH_NOTIFICATION_TYPES:
                mock_webpush.reset_mock()
                result = send_push_notification(
                    db=db_session,
                    user_id=test_user.id,
                    notification_type=ntype,
                    title=f"Test {ntype}",
                    body=f"Body for {ntype}",
                )
                assert result is True, f"Push should succeed for type '{ntype}'"
                mock_webpush.assert_called_once()


# --- Notification Service Integration Tests ---


class TestNotificationServicePushIntegration:
    """Tests that create_notification also triggers push delivery."""

    @patch("app.services.notification_service.send_push_notification")
    def test_create_notification_sends_push_by_default(
        self, mock_send_push, db_session: Session, test_user: User
    ):
        """create_notification calls push delivery when send_push=True (default)."""
        mock_send_push.return_value = True

        notification = create_notification(
            db=db_session,
            user_id=test_user.id,
            notification_type="daily_reminder",
            title="Log your spending!",
            body="Don't break your streak.",
            payload={"task_date": "2024-01-15"},
        )
        db_session.commit()

        assert notification.id is not None
        mock_send_push.assert_called_once()
        call_kwargs = mock_send_push.call_args.kwargs
        assert call_kwargs["notification_type"] == "daily_reminder"
        assert call_kwargs["title"] == "Log your spending!"
        assert call_kwargs["context"] == {"date": "2024-01-15"}

    @patch("app.services.notification_service.send_push_notification")
    def test_create_notification_skips_push_when_disabled(
        self, mock_send_push, db_session: Session, test_user: User
    ):
        """create_notification does not send push when send_push=False."""
        notification = create_notification(
            db=db_session,
            user_id=test_user.id,
            notification_type="budget_80",
            title="Budget Alert",
            body="80% used.",
            send_push=False,
        )
        db_session.commit()

        assert notification.id is not None
        mock_send_push.assert_not_called()

    @patch("app.services.notification_service.send_push_notification")
    def test_fallback_to_inapp_when_push_fails(
        self, mock_send_push, db_session: Session, test_user: User
    ):
        """In-app notification is still created even when push delivery fails."""
        mock_send_push.return_value = False

        notification = create_notification(
            db=db_session,
            user_id=test_user.id,
            notification_type="spike_alert",
            title="Spike!",
            body="Food spending spiked.",
            payload={"category_id": 3},
        )
        db_session.commit()

        # In-app notification is still created
        assert notification.id is not None
        assert notification.notification_type == "spike_alert"
        # Push was attempted
        mock_send_push.assert_called_once()


# --- API Endpoint Tests ---


class TestPushSubscriptionAPI:
    """Tests for POST /api/notifications/push-subscription."""

    def test_register_push_subscription_success(self, client: TestClient):
        """Successfully registers a push subscription."""
        response = client.post(
            "/api/notifications/push-subscription",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0Q",
                    "auth": "tBHItJI5svbpC7",
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == 1
        assert data["endpoint"] == "https://fcm.googleapis.com/fcm/send/abc123"
        assert "id" in data
        assert "created_at_utc" in data
        assert data["message"] == "Push subscription registered successfully."

    def test_register_push_subscription_missing_fields(self, client: TestClient):
        """Returns 422 when required fields are missing."""
        response = client.post(
            "/api/notifications/push-subscription",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
                # Missing 'keys'
            },
        )
        assert response.status_code == 422

    def test_register_push_subscription_updates_existing(self, client: TestClient):
        """Re-registering same endpoint updates keys."""
        endpoint = "https://fcm.googleapis.com/fcm/send/same"

        # First registration
        resp1 = client.post(
            "/api/notifications/push-subscription",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "old_key", "auth": "old_auth"},
            },
        )
        assert resp1.status_code == 201
        first_id = resp1.json()["id"]

        # Second registration (same endpoint)
        resp2 = client.post(
            "/api/notifications/push-subscription",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "new_key", "auth": "new_auth"},
            },
        )
        assert resp2.status_code == 201
        second_id = resp2.json()["id"]

        # Same record updated
        assert first_id == second_id
