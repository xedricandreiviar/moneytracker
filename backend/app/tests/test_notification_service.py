"""Tests for the notification service and API.

Covers:
- create_notification
- get_unread_notifications
- mark_as_read
- send_daily_reminder (at-most-once enforcement)
- GET /api/notifications
- PUT /api/notifications/{id}/read
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.daily_task import DailyTask
from app.models.notification import Notification
from app.models.user import User
from app.services.notification_service import (
    create_notification,
    get_unread_notifications,
    mark_as_read,
    send_daily_reminder,
)


# --- Test database setup ---

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(TEST_ENGINE)
    yield
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def test_db():
    """Provide a session bound to the shared test engine."""
    TestSession = sessionmaker(bind=TEST_ENGINE)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def client(test_db):
    """Create a test client with overridden database dependency."""

    def _override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db):
    """Create a test user in the database."""
    user = User(id=1, timezone="UTC", current_streak=0, version=1)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestCreateNotification:
    """Tests for create_notification service function."""

    def test_create_notification_basic(self, test_db, test_user):
        """Should create a notification with basic fields."""
        notif = create_notification(
            db=test_db,
            user_id=test_user.id,
            notification_type="daily_reminder",
            title="Don't forget!",
            body="Log your transactions today.",
        )
        test_db.commit()

        assert notif.id is not None
        assert notif.user_id == test_user.id
        assert notif.notification_type == "daily_reminder"
        assert notif.title == "Don't forget!"
        assert notif.body == "Log your transactions today."
        assert notif.is_read is False
        assert notif.payload_json is None

    def test_create_notification_with_payload(self, test_db, test_user):
        """Should create a notification with JSON payload."""
        payload = {"task_date": "2024-01-15", "streak": 5}
        notif = create_notification(
            db=test_db,
            user_id=test_user.id,
            notification_type="budget_80",
            title="Budget Warning",
            body="You've used 80% of your Food budget.",
            payload=payload,
        )
        test_db.commit()

        assert notif.payload_json is not None
        import json

        assert json.loads(notif.payload_json) == payload

    def test_create_notification_all_types(self, test_db, test_user):
        """Should support all valid notification types."""
        types = [
            "daily_reminder",
            "budget_80",
            "budget_100",
            "spike_alert",
            "weekly_summary",
            "monthly_summary",
            "ai_coaching",
        ]
        for ntype in types:
            notif = create_notification(
                db=test_db,
                user_id=test_user.id,
                notification_type=ntype,
                title=f"Test {ntype}",
                body=f"Body for {ntype}",
            )
            assert notif.notification_type == ntype
        test_db.commit()


class TestGetUnreadNotifications:
    """Tests for get_unread_notifications service function."""

    def test_returns_empty_when_no_notifications(self, test_db, test_user):
        """Should return empty list when user has no notifications."""
        result = get_unread_notifications(db=test_db, user_id=test_user.id)
        assert result == []

    def test_returns_only_unread(self, test_db, test_user):
        """Should return only unread notifications."""
        # Create a read notification
        read_notif = Notification(
            user_id=test_user.id,
            notification_type="budget_80",
            title="Read Notif",
            body="Already read",
            is_read=True,
        )
        # Create an unread notification
        unread_notif = Notification(
            user_id=test_user.id,
            notification_type="spike_alert",
            title="Unread Notif",
            body="Not yet read",
            is_read=False,
        )
        test_db.add_all([read_notif, unread_notif])
        test_db.commit()

        result = get_unread_notifications(db=test_db, user_id=test_user.id)
        assert len(result) == 1
        assert result[0].title == "Unread Notif"

    def test_orders_newest_first(self, test_db, test_user):
        """Should return notifications ordered by created_at_utc descending."""
        older = Notification(
            user_id=test_user.id,
            notification_type="daily_reminder",
            title="Older",
            body="Older notification",
            is_read=False,
            created_at_utc=datetime(2024, 1, 1, 10, 0, 0),
        )
        newer = Notification(
            user_id=test_user.id,
            notification_type="daily_reminder",
            title="Newer",
            body="Newer notification",
            is_read=False,
            created_at_utc=datetime(2024, 1, 2, 10, 0, 0),
        )
        test_db.add_all([older, newer])
        test_db.commit()

        result = get_unread_notifications(db=test_db, user_id=test_user.id)
        assert len(result) == 2
        assert result[0].title == "Newer"
        assert result[1].title == "Older"

    def test_does_not_return_other_users_notifications(self, test_db, test_user):
        """Should only return notifications for the specified user."""
        # Create another user
        other_user = User(id=2, timezone="UTC", current_streak=0, version=1)
        test_db.add(other_user)
        test_db.commit()

        # Add notification for other user
        notif = Notification(
            user_id=other_user.id,
            notification_type="spike_alert",
            title="Other User's Notif",
            body="Should not appear",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()

        result = get_unread_notifications(db=test_db, user_id=test_user.id)
        assert len(result) == 0


class TestMarkAsRead:
    """Tests for mark_as_read service function."""

    def test_mark_as_read_success(self, test_db, test_user):
        """Should mark a notification as read."""
        notif = Notification(
            user_id=test_user.id,
            notification_type="budget_100",
            title="Budget Exceeded",
            body="Your Food budget is exceeded.",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()
        test_db.refresh(notif)

        result = mark_as_read(db=test_db, notification_id=notif.id, user_id=test_user.id)
        test_db.commit()

        assert result is not None
        assert result.is_read is True

    def test_mark_as_read_not_found(self, test_db, test_user):
        """Should return None for non-existent notification."""
        result = mark_as_read(db=test_db, notification_id=9999, user_id=test_user.id)
        assert result is None

    def test_mark_as_read_wrong_user(self, test_db, test_user):
        """Should return None if notification belongs to a different user."""
        other_user = User(id=2, timezone="UTC", current_streak=0, version=1)
        test_db.add(other_user)
        test_db.commit()

        notif = Notification(
            user_id=other_user.id,
            notification_type="spike_alert",
            title="Other's Notif",
            body="Not yours",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()
        test_db.refresh(notif)

        result = mark_as_read(db=test_db, notification_id=notif.id, user_id=test_user.id)
        assert result is None


class TestSendDailyReminder:
    """Tests for send_daily_reminder with at-most-once enforcement."""

    def test_sends_reminder_for_pending_task(self, test_db, test_user):
        """Should send reminder when task is pending."""
        today = date.today()
        task = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="pending",
        )
        test_db.add(task)
        test_db.commit()

        result = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        test_db.commit()

        assert result is not None
        assert result.notification_type == "daily_reminder"
        assert result.user_id == test_user.id

    def test_sends_reminder_for_grace_period_task(self, test_db, test_user):
        """Should send reminder when task is in grace_period."""
        today = date.today()
        task = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="grace_period",
        )
        test_db.add(task)
        test_db.commit()

        result = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        test_db.commit()

        assert result is not None
        assert result.notification_type == "daily_reminder"

    def test_does_not_send_for_completed_task(self, test_db, test_user):
        """Should not send reminder when task is already completed."""
        today = date.today()
        task = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="completed",
            completion_type="transaction_logged",
        )
        test_db.add(task)
        test_db.commit()

        result = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        assert result is None

    def test_does_not_send_for_missed_task(self, test_db, test_user):
        """Should not send reminder when task is missed."""
        today = date.today()
        task = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="missed",
        )
        test_db.add(task)
        test_db.commit()

        result = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        assert result is None

    def test_does_not_send_when_no_task(self, test_db, test_user):
        """Should not send reminder when no daily task exists for the date."""
        today = date.today()
        result = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        assert result is None

    def test_at_most_once_per_day(self, test_db, test_user):
        """Should enforce at-most-one reminder per day per user."""
        today = date.today()
        task = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="pending",
        )
        test_db.add(task)
        test_db.commit()

        # First reminder should succeed
        result1 = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        test_db.commit()
        assert result1 is not None

        # Second attempt should be suppressed
        result2 = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        assert result2 is None

    def test_allows_reminder_on_different_days(self, test_db, test_user):
        """Should allow one reminder per day (not a total of one ever)."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()

        # Create tasks for both days
        task_yesterday = DailyTask(
            user_id=test_user.id,
            task_date=yesterday,
            status="pending",
        )
        task_today = DailyTask(
            user_id=test_user.id,
            task_date=today,
            status="pending",
        )
        test_db.add_all([task_yesterday, task_today])
        test_db.commit()

        # Send reminder for yesterday
        result1 = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=yesterday)
        test_db.commit()
        assert result1 is not None

        # Send reminder for today — should also succeed (different day)
        result2 = send_daily_reminder(db=test_db, user_id=test_user.id, task_date=today)
        test_db.commit()
        assert result2 is not None


class TestNotificationAPI:
    """Tests for notification API endpoints."""

    def test_get_notifications_empty(self, client, test_user):
        """Should return empty list when no unread notifications."""
        response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["notifications"] == []
        assert data["count"] == 0

    def test_get_notifications_returns_unread(self, client, test_db, test_user):
        """Should return unread notifications."""
        notif = Notification(
            user_id=test_user.id,
            notification_type="spike_alert",
            title="Spending Spike: Food",
            body="Your Food spending is above average.",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()

        response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["notifications"][0]["title"] == "Spending Spike: Food"
        assert data["notifications"][0]["notification_type"] == "spike_alert"
        assert data["notifications"][0]["is_read"] is False

    def test_get_notifications_excludes_read(self, client, test_db, test_user):
        """Should not return read notifications."""
        notif = Notification(
            user_id=test_user.id,
            notification_type="budget_80",
            title="Budget Warning",
            body="80% used",
            is_read=True,
        )
        test_db.add(notif)
        test_db.commit()

        response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    def test_get_notifications_with_payload(self, client, test_db, test_user):
        """Should return notification payload as parsed JSON."""
        import json

        notif = Notification(
            user_id=test_user.id,
            notification_type="weekly_summary",
            title="Summary Ready",
            body="Your weekly summary is ready.",
            payload_json=json.dumps({"total_spent": 50000}),
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()

        response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["notifications"][0]["payload"] == {"total_spent": 50000}

    def test_mark_as_read_success(self, client, test_db, test_user):
        """Should mark notification as read and return success."""
        notif = Notification(
            user_id=test_user.id,
            notification_type="daily_reminder",
            title="Reminder",
            body="Log today",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()
        test_db.refresh(notif)

        response = client.put(f"/api/notifications/{notif.id}/read")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == notif.id
        assert data["is_read"] is True
        assert data["message"] == "Notification marked as read."

    def test_mark_as_read_not_found(self, client, test_user):
        """Should return 404 for non-existent notification."""
        response = client.put("/api/notifications/9999/read")

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found."

    def test_mark_as_read_removes_from_unread_list(self, client, test_db, test_user):
        """After marking as read, notification should not appear in unread list."""
        notif = Notification(
            user_id=test_user.id,
            notification_type="ai_coaching",
            title="Coaching Tip",
            body="Consider reducing Food spending.",
            is_read=False,
        )
        test_db.add(notif)
        test_db.commit()
        test_db.refresh(notif)

        # Verify it's in the list first
        response1 = client.get("/api/notifications")
        assert response1.json()["count"] == 1

        # Mark as read
        client.put(f"/api/notifications/{notif.id}/read")

        # Verify it's gone from unread list
        response2 = client.get("/api/notifications")
        assert response2.json()["count"] == 0
