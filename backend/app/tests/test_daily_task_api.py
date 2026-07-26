"""Tests for daily task and streak API endpoints.

Covers:
- GET /api/daily-task
- POST /api/daily-task/complete
- GET /api/streak
- Scheduler job: generate_daily_tasks_job
- Transaction auto-complete wiring
"""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.daily_task import DailyTask, DailyTaskCompletionType, DailyTaskStatus
from app.models.user import User


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
    """Create a test user with ID=1."""
    u = User(id=1, timezone="UTC", current_streak=5, version=1, profile_completed=True)
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)
    return u


@pytest.fixture
def today_task(test_db, user):
    """Create a pending daily task for today."""
    today = datetime.now(timezone.utc).date()
    task = DailyTask(
        user_id=user.id,
        task_date=today,
        status=DailyTaskStatus.pending,
        created_at_utc=datetime.now(timezone.utc),
    )
    test_db.add(task)
    test_db.commit()
    test_db.refresh(task)
    return task


class TestGetDailyTask:
    """Tests for GET /api/daily-task endpoint."""

    def test_get_daily_task_returns_current_task(self, client, user, today_task):
        """Should return the current daily task with hours remaining."""
        response = client.get("/api/daily-task")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == today_task.id
        assert data["user_id"] == user.id
        assert data["status"] == "pending"
        assert data["completion_type"] is None
        assert "hours_remaining" in data
        assert data["hours_remaining"] >= 0

    def test_get_daily_task_no_task_returns_404(self, client, user):
        """Should return 404 when no task exists for today."""
        response = client.get("/api/daily-task")
        assert response.status_code == 404

    def test_get_daily_task_completed_shows_status(self, client, user, test_db):
        """Should return completed task with completion info."""
        today = datetime.now(timezone.utc).date()
        task = DailyTask(
            user_id=user.id,
            task_date=today,
            status=DailyTaskStatus.completed,
            completion_type=DailyTaskCompletionType.transaction_logged,
            completed_at_utc=datetime.now(timezone.utc),
            created_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(task)
        test_db.commit()

        response = client.get("/api/daily-task")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "completed"
        assert data["completion_type"] == "transaction_logged"


class TestCompleteDailyTask:
    """Tests for POST /api/daily-task/complete endpoint."""

    def test_complete_task_marks_no_transactions(self, client, user, today_task):
        """Should mark the task as completed with 'no_transactions'."""
        response = client.post("/api/daily-task/complete")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "completed"
        assert data["completion_type"] == "no_transactions"
        assert data["id"] == today_task.id

    def test_complete_task_increments_streak(self, client, user, today_task, test_db):
        """Should increment the user's streak on completion."""
        initial_streak = user.current_streak
        response = client.post("/api/daily-task/complete")
        assert response.status_code == 200

        test_db.refresh(user)
        assert user.current_streak == initial_streak + 1

    def test_complete_task_no_task_returns_404(self, client, user):
        """Should return 404 when no task exists for today."""
        response = client.post("/api/daily-task/complete")
        assert response.status_code == 404

    def test_complete_task_already_completed_returns_400(self, client, user, test_db):
        """Should return 400 when the task is already completed."""
        today = datetime.now(timezone.utc).date()
        task = DailyTask(
            user_id=user.id,
            task_date=today,
            status=DailyTaskStatus.completed,
            completion_type=DailyTaskCompletionType.no_transactions,
            completed_at_utc=datetime.now(timezone.utc),
            created_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(task)
        test_db.commit()

        response = client.post("/api/daily-task/complete")
        assert response.status_code == 400
        assert "already completed" in response.json()["detail"]

    def test_complete_task_missed_returns_400(self, client, user, test_db):
        """Should return 400 when the task has been missed."""
        today = datetime.now(timezone.utc).date()
        task = DailyTask(
            user_id=user.id,
            task_date=today,
            status=DailyTaskStatus.missed,
            created_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(task)
        test_db.commit()

        response = client.post("/api/daily-task/complete")
        assert response.status_code == 400
        assert "missed" in response.json()["detail"]


class TestGetStreak:
    """Tests for GET /api/streak endpoint."""

    def test_get_streak_returns_current_count(self, client, user):
        """Should return the current streak count."""
        response = client.get("/api/streak")
        assert response.status_code == 200

        data = response.json()
        assert data["current_streak"] == user.current_streak
        assert "grace_period_active" in data

    def test_get_streak_no_grace_period(self, client, user):
        """Should show grace_period_active=False when no missed day."""
        response = client.get("/api/streak")
        assert response.status_code == 200

        data = response.json()
        assert data["grace_period_active"] is False
        assert data["grace_remaining_hours"] == 0.0


class TestTransactionAutoComplete:
    """Tests for auto-completing daily task on transaction creation."""

    def test_transaction_auto_completes_daily_task(self, client, user, today_task, test_db):
        """Creating a transaction should auto-complete the daily task."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 1500,
                "direction": "spent",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        # Refresh the task from DB
        test_db.refresh(today_task)
        assert today_task.status == DailyTaskStatus.completed
        assert today_task.completion_type == DailyTaskCompletionType.transaction_logged

    def test_transaction_does_not_fail_without_task(self, client, user):
        """Creating a transaction should succeed even if no daily task exists."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 1500,
                "direction": "spent",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201


class TestSchedulerJob:
    """Tests for the daily task generation scheduler job."""

    def test_job_creates_task_for_user(self, test_db, user):
        """The scheduler job should create a daily task for users without one."""
        from app.jobs.daily_task_job import generate_daily_tasks_job

        user_id = user.id  # Capture ID before potential detachment

        # Patch SessionLocal to return our test session
        with patch("app.jobs.daily_task_job.SessionLocal", return_value=test_db):
            generate_daily_tasks_job()

        today = datetime.now(timezone.utc).date()
        task = (
            test_db.query(DailyTask)
            .filter(DailyTask.user_id == user_id, DailyTask.task_date == today)
            .first()
        )
        assert task is not None
        assert task.status == DailyTaskStatus.pending

    def test_job_is_idempotent(self, test_db, user, today_task):
        """Running the job twice should not create duplicate tasks."""
        from app.jobs.daily_task_job import generate_daily_tasks_job

        user_id = user.id
        today = datetime.now(timezone.utc).date()

        with patch("app.jobs.daily_task_job.SessionLocal", return_value=test_db):
            generate_daily_tasks_job()

        tasks = (
            test_db.query(DailyTask)
            .filter(DailyTask.user_id == user_id, DailyTask.task_date == today)
            .all()
        )
        assert len(tasks) == 1
