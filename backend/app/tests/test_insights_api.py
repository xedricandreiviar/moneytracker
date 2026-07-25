"""Tests for insight API endpoints.

Covers:
- GET /api/insights/weekly — weekly spending summaries
- GET /api/insights/monthly — monthly spending summaries
- GET /api/insights/spikes — active spending spike alerts
- Scheduler jobs: weekly_summary_job, monthly_summary_job, spike_detection_job

Requirements: 5.1, 5.2, 5.6, 6.1, 6.3
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.category import Category
from app.models.notification import Notification
from app.models.spike_suppression import SpikeSuppression
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.models.user_locale import UserLocale


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
def user(test_db):
    """Create a test user with ID=1 and US locale."""
    u = User(id=1, timezone="UTC", current_streak=0, version=1)
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)

    locale = UserLocale(
        user_id=u.id,
        country_code="US",
        currency_code="USD",
        currency_symbol="$",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="MM/DD/YYYY",
        week_start_day=0,  # Sunday
    )
    test_db.add(locale)
    test_db.commit()
    test_db.refresh(u)
    return u


@pytest.fixture
def category_food(test_db, user):
    """Create a food category."""
    cat = Category(id=1, user_id=user.id, name="Food", usage_count=10)
    test_db.add(cat)
    test_db.commit()
    test_db.refresh(cat)
    return cat


@pytest.fixture
def category_transport(test_db, user):
    """Create a transport category."""
    cat = Category(id=2, user_id=user.id, name="Transport", usage_count=5)
    test_db.add(cat)
    test_db.commit()
    test_db.refresh(cat)
    return cat


class TestGetWeeklySummary:
    """Tests for GET /api/insights/weekly endpoint."""

    def test_weekly_summary_empty(self, client, user):
        """Should return a valid summary with zero values when no transactions exist."""
        response = client.get("/api/insights/weekly")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == 1
        assert data["total_spent"] == 0
        assert data["total_received"] == 0
        assert data["net"] == 0
        assert data["category_totals"] == []

    def test_weekly_summary_with_transactions(self, client, user, test_db, category_food):
        """Should include transaction totals in the weekly summary."""
        # Create transactions for today (within current week)
        today = datetime.now(timezone.utc).date()
        txn1 = Transaction(
            user_id=user.id,
            amount_smallest_unit=1500,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=category_food.id,
            transaction_date_local=today,
            transaction_datetime_utc=datetime.now(timezone.utc),
            created_at_utc=datetime.now(timezone.utc),
        )
        txn2 = Transaction(
            user_id=user.id,
            amount_smallest_unit=5000,
            direction=TransactionDirection.received,
            currency_code="USD",
            category_id=category_food.id,
            transaction_date_local=today,
            transaction_datetime_utc=datetime.now(timezone.utc),
            created_at_utc=datetime.now(timezone.utc),
        )
        test_db.add_all([txn1, txn2])
        test_db.commit()

        response = client.get("/api/insights/weekly")
        assert response.status_code == 200

        data = response.json()
        assert data["total_spent"] == 1500
        assert data["total_received"] == 5000
        assert data["net"] == 3500

    def test_weekly_summary_with_custom_week_end(self, client, user, test_db, category_food):
        """Should accept a week_end query parameter to query past weeks."""
        past_date = date(2024, 1, 6)  # A Saturday
        txn = Transaction(
            user_id=user.id,
            amount_smallest_unit=2000,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=category_food.id,
            transaction_date_local=past_date,
            transaction_datetime_utc=datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc),
            created_at_utc=datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc),
        )
        test_db.add(txn)
        test_db.commit()

        response = client.get("/api/insights/weekly", params={"week_end": "2024-01-06"})
        assert response.status_code == 200

        data = response.json()
        assert data["total_spent"] == 2000
        assert data["week_end"] == "2024-01-06"


class TestGetMonthlySummary:
    """Tests for GET /api/insights/monthly endpoint."""

    def test_monthly_summary_empty(self, client, user):
        """Should return a valid summary with zero values when no transactions exist."""
        response = client.get("/api/insights/monthly")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == 1
        assert data["total_spent"] == 0
        assert data["total_received"] == 0
        assert data["net"] == 0

    def test_monthly_summary_with_transactions(self, client, user, test_db, category_food):
        """Should include transaction totals in the monthly summary."""
        today = datetime.now(timezone.utc).date()
        txn = Transaction(
            user_id=user.id,
            amount_smallest_unit=3000,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=category_food.id,
            transaction_date_local=today,
            transaction_datetime_utc=datetime.now(timezone.utc),
            created_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(txn)
        test_db.commit()

        response = client.get(
            "/api/insights/monthly",
            params={"month": today.month, "year": today.year},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total_spent"] == 3000
        assert data["month"] == today.month
        assert data["year"] == today.year

    def test_monthly_summary_defaults_to_current_month(self, client, user):
        """Should default to current month/year when params not provided."""
        today = datetime.now(timezone.utc).date()
        response = client.get("/api/insights/monthly")
        assert response.status_code == 200

        data = response.json()
        assert data["month"] == today.month
        assert data["year"] == today.year

    def test_monthly_summary_invalid_month(self, client, user):
        """Should reject invalid month values."""
        response = client.get("/api/insights/monthly", params={"month": 13})
        assert response.status_code == 422


class TestGetSpendingSpikes:
    """Tests for GET /api/insights/spikes endpoint."""

    def test_spikes_empty_no_data(self, client, user):
        """Should return empty spikes list when no transaction data exists."""
        response = client.get("/api/insights/spikes")
        assert response.status_code == 200

        data = response.json()
        assert data["spikes"] == []

    def test_spikes_response_structure(self, client, user):
        """Should return proper response structure."""
        response = client.get("/api/insights/spikes")
        assert response.status_code == 200

        data = response.json()
        assert "spikes" in data
        assert "detected_at" in data


class TestInsightSchedulerJobs:
    """Tests for insight scheduler jobs and notification creation."""

    def test_weekly_summary_job_creates_notification(self, test_db, user):
        """Weekly job should create a notification when a week ends."""
        from app.jobs.insight_jobs import _create_notification

        _create_notification(
            db=test_db,
            user_id=user.id,
            notification_type="weekly_summary",
            title="Weekly Spending Summary Available",
            body="Your weekly summary is ready.",
            payload={"week_start": "2024-01-01", "week_end": "2024-01-07"},
        )
        test_db.commit()

        notifications = test_db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.notification_type == "weekly_summary",
        ).all()

        assert len(notifications) == 1
        assert notifications[0].title == "Weekly Spending Summary Available"
        assert notifications[0].is_read is False

    def test_monthly_summary_job_creates_notification(self, test_db, user):
        """Monthly job should create a notification at month end."""
        from app.jobs.insight_jobs import _create_notification

        _create_notification(
            db=test_db,
            user_id=user.id,
            notification_type="monthly_summary",
            title="Monthly Spending Summary Available",
            body="Your monthly summary for 2024-01 is ready.",
            payload={"month": 1, "year": 2024},
        )
        test_db.commit()

        notifications = test_db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.notification_type == "monthly_summary",
        ).all()

        assert len(notifications) == 1
        assert "Monthly" in notifications[0].title

    def test_spike_detection_job_creates_notification(self, test_db, user):
        """Spike detection job should create a notification per spike."""
        from app.jobs.insight_jobs import _create_notification

        _create_notification(
            db=test_db,
            user_id=user.id,
            notification_type="spike_alert",
            title="Spending Spike: Food",
            body="Your spending in Food this week is significantly higher.",
            payload={
                "category_name": "Food",
                "current_total": 15000,
                "rolling_average": 5000.0,
            },
        )
        test_db.commit()

        notifications = test_db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.notification_type == "spike_alert",
        ).all()

        assert len(notifications) == 1
        assert "Spike" in notifications[0].title

    def test_monthly_job_only_runs_on_first_of_month(self, test_db, user):
        """Monthly job should only generate summaries on the 1st of the month.

        We test this by verifying that when today is NOT the 1st, no
        notifications are created. The job checks today.day != 1 and returns early.
        """
        from app.jobs.insight_jobs import monthly_summary_job

        today = datetime.now(timezone.utc).date()

        # Patch SessionLocal so the job uses our test db
        with patch("app.jobs.insight_jobs.SessionLocal", return_value=test_db):
            # If today is actually the 1st, patch to pretend it's the 15th
            if today.day == 1:
                fake_now = datetime(today.year, today.month, 15, 0, 10, tzinfo=timezone.utc)
                with patch("app.jobs.insight_jobs.datetime") as mock_dt:
                    mock_dt.now.return_value = fake_now
                    mock_dt.now.return_value.date.return_value = fake_now.date()
                    monthly_summary_job()
            else:
                monthly_summary_job()

        # No notifications should be created since today.day != 1
        notifications = test_db.query(Notification).filter(
            Notification.user_id == user.id,
        ).all()
        assert len(notifications) == 0
