"""Tests for budget API endpoints.

Covers: GET /api/budgets, POST /api/budgets, PUT /api/budgets/{id},
DELETE /api/budgets/{id}, and error handling (422, 409, 404).
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus, BudgetPeriodType
from app.models.category import Category
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
def test_user(test_db):
    """Create a test user in the database."""
    user = User(id=1, timezone="UTC", current_streak=0, version=1, profile_completed=True)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_with_locale(test_db, test_user):
    """Create a test user with a US locale configured."""
    locale = UserLocale(
        user_id=test_user.id,
        country_code="US",
        currency_code="USD",
        currency_symbol="$",
        decimal_precision=2,
        decimal_separator=".",
        thousands_separator=",",
        date_format="MM/DD/YYYY",
        week_start_day=0,
    )
    test_db.add(locale)
    test_db.commit()
    return test_user


@pytest.fixture
def test_category(test_db, test_user):
    """Create a test category."""
    category = Category(
        user_id=test_user.id,
        name="Food",
        usage_count=5,
        last_used_at_utc=datetime.utcnow(),
    )
    test_db.add(category)
    test_db.commit()
    test_db.refresh(category)
    return category


class TestCreateBudget:
    """Tests for POST /api/budgets."""

    def test_create_budget_monthly_overall(self, client, test_user_with_locale):
        """Should create a monthly overall budget successfully."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["user_id"] == 1
        assert data["period_type"] == "monthly"
        assert data["limit_smallest_unit"] == 100000
        assert data["currency_code"] == "USD"
        assert data["category_id"] is None
        assert data["is_active"] is True
        assert data["current_period"] is not None
        assert data["projection"] is not None

    def test_create_budget_weekly_with_category(self, client, test_user_with_locale, test_category):
        """Should create a weekly budget for a specific category."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "weekly",
                "limit_smallest_unit": 25000,
                "currency_code": "USD",
                "category_id": test_category.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["period_type"] == "weekly"
        assert data["limit_smallest_unit"] == 25000
        assert data["category_id"] == test_category.id

    def test_create_budget_returns_period_info(self, client, test_user_with_locale):
        """Should include current period and projection in response."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 50000,
                "currency_code": "USD",
            },
        )

        assert response.status_code == 201
        data = response.json()
        period = data["current_period"]
        assert period is not None
        assert period["spent_smallest_unit"] == 0
        assert period["status"] == "active"

        projection = data["projection"]
        assert projection is not None
        assert projection["status"] == "on_track"
        assert projection["overage"] == 0

    def test_create_budget_duplicate_returns_409(self, client, test_user_with_locale):
        """Should return 409 when creating a duplicate budget for same scope/period."""
        # Create first budget
        response1 = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 200000,
                "currency_code": "USD",
            },
        )
        assert response2.status_code == 409
        data = response2.json()
        assert "detail" in data

    def test_create_budget_invalid_period_type_returns_422(self, client, test_user_with_locale):
        """Should return 422 for invalid period type."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "daily",
                "limit_smallest_unit": 5000,
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_budget_zero_limit_returns_422(self, client, test_user_with_locale):
        """Should return 422 for zero limit."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 0,
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_budget_negative_limit_returns_422(self, client, test_user_with_locale):
        """Should return 422 for negative limit."""
        response = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": -100,
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_budget_different_periods_allowed(self, client, test_user_with_locale):
        """Should allow creating budgets with different period types for same scope."""
        response1 = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        assert response1.status_code == 201

        response2 = client.post(
            "/api/budgets",
            json={
                "period_type": "weekly",
                "limit_smallest_unit": 25000,
                "currency_code": "USD",
            },
        )
        assert response2.status_code == 201


class TestListBudgets:
    """Tests for GET /api/budgets."""

    def test_list_budgets_empty(self, client, test_user):
        """Should return empty list when no budgets exist."""
        response = client.get("/api/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["budgets"] == []
        assert data["count"] == 0

    def test_list_budgets_returns_active(self, client, test_user_with_locale):
        """Should return active budgets with projection."""
        # Create a budget
        client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )

        response = client.get("/api/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        budget = data["budgets"][0]
        assert budget["is_active"] is True
        assert budget["projection"] is not None

    def test_list_budgets_excludes_inactive(self, client, test_user_with_locale):
        """Should not return deactivated budgets."""
        # Create and deactivate a budget
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]
        client.delete(f"/api/budgets/{budget_id}")

        response = client.get("/api/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    def test_list_budgets_multiple(self, client, test_user_with_locale, test_category):
        """Should return multiple active budgets."""
        # Create overall monthly budget
        client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        # Create category weekly budget
        client.post(
            "/api/budgets",
            json={
                "period_type": "weekly",
                "limit_smallest_unit": 15000,
                "currency_code": "USD",
                "category_id": test_category.id,
            },
        )

        response = client.get("/api/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2


class TestUpdateBudget:
    """Tests for PUT /api/budgets/{id}."""

    def test_update_budget_limit(self, client, test_user_with_locale):
        """Should update the budget limit successfully."""
        # Create a budget
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]

        # Update the limit
        response = client.put(
            f"/api/budgets/{budget_id}",
            json={"limit_smallest_unit": 150000},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit_smallest_unit"] == 150000

    def test_update_budget_not_found_returns_404(self, client, test_user):
        """Should return 404 for non-existent budget."""
        response = client.put(
            "/api/budgets/9999",
            json={"limit_smallest_unit": 50000},
        )

        assert response.status_code == 404

    def test_update_budget_invalid_limit_returns_422(self, client, test_user_with_locale):
        """Should return 422 for invalid (zero/negative) limit."""
        # Create a budget
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]

        # Attempt invalid update
        response = client.put(
            f"/api/budgets/{budget_id}",
            json={"limit_smallest_unit": 0},
        )

        assert response.status_code == 422

    def test_update_deactivated_budget_returns_404(self, client, test_user_with_locale):
        """Should return 404 when trying to update a deactivated budget."""
        # Create and deactivate
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]
        client.delete(f"/api/budgets/{budget_id}")

        # Attempt update
        response = client.put(
            f"/api/budgets/{budget_id}",
            json={"limit_smallest_unit": 150000},
        )

        assert response.status_code == 404


class TestDeactivateBudget:
    """Tests for DELETE /api/budgets/{id}."""

    def test_deactivate_budget_success(self, client, test_user_with_locale):
        """Should deactivate a budget and return success."""
        # Create a budget
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]

        # Deactivate
        response = client.delete(f"/api/budgets/{budget_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["detail"] == "Budget deactivated."
        assert data["id"] == budget_id

    def test_deactivate_budget_not_found_returns_404(self, client, test_user):
        """Should return 404 for non-existent budget."""
        response = client.delete("/api/budgets/9999")

        assert response.status_code == 404

    def test_deactivate_budget_removes_from_list(self, client, test_user_with_locale):
        """Should remove the budget from the active list."""
        # Create a budget
        create_resp = client.post(
            "/api/budgets",
            json={
                "period_type": "monthly",
                "limit_smallest_unit": 100000,
                "currency_code": "USD",
            },
        )
        budget_id = create_resp.json()["id"]

        # Verify it's in the list
        list_resp = client.get("/api/budgets")
        assert list_resp.json()["count"] == 1

        # Deactivate
        client.delete(f"/api/budgets/{budget_id}")

        # Verify it's no longer in the list
        list_resp = client.get("/api/budgets")
        assert list_resp.json()["count"] == 0
