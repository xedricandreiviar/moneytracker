"""Tests for Dashboard API endpoints.

Covers:
- GET /api/dashboard/summary?period={daily|weekly|monthly}
- GET /api/dashboard/insight
- Profile-not-completed gating (400 responses)
- Period validation

Requirements covered: 18.1, 18.2, 18.3, 18.4
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.budget import Budget, BudgetPeriodType
from app.models.category import Category
from app.models.category_weight import CategoryWeight
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import CommuteMethod, EmploymentStatus, User
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
    """Create a test user with profile completed."""
    user = User(
        id=1,
        timezone="UTC",
        current_streak=0,
        version=1,
        profile_completed=True,
        employment_status=EmploymentStatus.working,
        commute_method=CommuteMethod.public_transit,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_incomplete_profile(test_db):
    """Create a test user with profile NOT completed."""
    user = User(
        id=1,
        timezone="UTC",
        current_streak=0,
        version=1,
        profile_completed=False,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_with_locale(test_db, test_user):
    """Create a test user with US locale configured."""
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
    test_db.refresh(test_user)
    return test_user


@pytest.fixture
def test_weights(test_db, test_user):
    """Create category weight entries for the test user."""
    weights = [
        CategoryWeight(
            user_id=test_user.id,
            category_name="Savings",
            weight_percentage=Decimal("30.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=test_user.id,
            category_name="Food",
            weight_percentage=Decimal("25.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=test_user.id,
            category_name="Transportation",
            weight_percentage=Decimal("20.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=test_user.id,
            category_name="Wants",
            weight_percentage=Decimal("25.00"),
            is_manual_override=False,
        ),
    ]
    for w in weights:
        test_db.add(w)
    test_db.commit()
    return weights


@pytest.fixture
def test_category_food(test_db, test_user):
    """Create a Food category."""
    category = Category(
        user_id=test_user.id,
        name="Food",
        usage_count=5,
    )
    test_db.add(category)
    test_db.commit()
    test_db.refresh(category)
    return category


@pytest.fixture
def test_transactions(test_db, test_user, test_category_food):
    """Create transactions for today."""
    today = datetime.now(timezone.utc).date()
    txns = [
        Transaction(
            user_id=test_user.id,
            amount_smallest_unit=5000,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=test_category_food.id,
            transaction_date_local=today,
            transaction_datetime_utc=datetime.now(timezone.utc),
        ),
        Transaction(
            user_id=test_user.id,
            amount_smallest_unit=100000,
            direction=TransactionDirection.received,
            currency_code="USD",
            category_id=None,
            transaction_date_local=today,
            transaction_datetime_utc=datetime.now(timezone.utc),
        ),
    ]
    for txn in txns:
        test_db.add(txn)
    test_db.commit()
    return txns


class TestDashboardSummary:
    """Tests for GET /api/dashboard/summary."""

    def test_daily_summary_returns_data(
        self, client, test_user_with_locale, test_transactions
    ):
        """Daily summary returns correct totals for today."""
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "daily"
        assert data["total_income"] == 100000
        assert data["total_expenses"] == 5000
        assert data["balance"] == 95000

    def test_weekly_summary_returns_data(
        self, client, test_user_with_locale, test_transactions
    ):
        """Weekly summary returns data for the current week."""
        response = client.get("/api/dashboard/summary?period=weekly")
        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "weekly"
        assert data["total_income"] >= 0
        assert data["total_expenses"] >= 0

    def test_monthly_summary_returns_data(
        self, client, test_user_with_locale, test_transactions
    ):
        """Monthly summary returns data for the current month."""
        response = client.get("/api/dashboard/summary?period=monthly")
        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "monthly"
        assert data["total_income"] >= 0
        assert data["total_expenses"] >= 0

    def test_invalid_period_returns_422(self, client, test_user_with_locale):
        """Invalid period value returns 422."""
        response = client.get("/api/dashboard/summary?period=yearly")
        assert response.status_code == 422

    def test_missing_period_returns_422(self, client, test_user_with_locale):
        """Missing period param returns 422."""
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 422

    def test_profile_not_completed_returns_403(
        self, client, test_user_incomplete_profile
    ):
        """Profile not completed is gated by middleware returning 403."""
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code == 403
        assert "Profile onboarding required" in response.json()["detail"]

    def test_summary_includes_category_breakdown(
        self, client, test_user_with_locale, test_transactions, test_weights
    ):
        """Summary includes per-category breakdown with weight percentages."""
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code == 200
        data = response.json()
        assert "category_breakdown" in data
        # We have a Food transaction so Food should appear
        food_items = [
            item for item in data["category_breakdown"]
            if item["category_name"] == "Food"
        ]
        assert len(food_items) == 1
        assert food_items[0]["total_spent"] == 5000
        assert food_items[0]["weight_percentage"] == "25.00"

    def test_empty_period_returns_zero_totals(
        self, client, test_user_with_locale
    ):
        """Period with no transactions returns zero totals."""
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code == 200
        data = response.json()
        assert data["total_income"] == 0
        assert data["total_expenses"] == 0
        assert data["balance"] == 0
        assert data["category_breakdown"] == []


class TestDashboardInsight:
    """Tests for GET /api/dashboard/insight."""

    def test_insight_returns_personalized_text(
        self, client, test_user_with_locale, test_weights
    ):
        """Insight endpoint returns text based on highest-weight category."""
        response = client.get("/api/dashboard/insight")
        assert response.status_code == 200
        data = response.json()
        assert "insight_text" in data
        assert data["category_focus"] == "Savings"  # Savings has 30%
        assert "Savings" in data["insight_text"]

    def test_insight_profile_not_completed_returns_403(
        self, client, test_user_incomplete_profile
    ):
        """Profile not completed is gated by middleware returning 403."""
        response = client.get("/api/dashboard/insight")
        assert response.status_code == 403
        assert "Profile onboarding required" in response.json()["detail"]

    def test_insight_no_weights_returns_fallback(
        self, client, test_user_with_locale
    ):
        """No weights returns a fallback insight message."""
        response = client.get("/api/dashboard/insight")
        assert response.status_code == 200
        data = response.json()
        assert "insight_text" in data
        assert data["category_focus"] is None
        assert "lifestyle profile" in data["insight_text"].lower()

    def test_insight_highest_weight_category_focus(
        self, client, test_user_with_locale, test_db, test_user
    ):
        """Insight focuses on the category with highest weight."""
        # Create weights where Transportation is highest
        weights = [
            CategoryWeight(
                user_id=test_user.id,
                category_name="Transportation",
                weight_percentage=Decimal("40.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=test_user.id,
                category_name="Savings",
                weight_percentage=Decimal("20.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=test_user.id,
                category_name="Food",
                weight_percentage=Decimal("20.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=test_user.id,
                category_name="Wants",
                weight_percentage=Decimal("20.00"),
                is_manual_override=False,
            ),
        ]
        for w in weights:
            test_db.add(w)
        test_db.commit()

        response = client.get("/api/dashboard/insight")
        assert response.status_code == 200
        data = response.json()
        assert data["category_focus"] == "Transportation"
        assert "Transportation" in data["insight_text"]
