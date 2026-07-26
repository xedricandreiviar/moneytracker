"""Integration tests for income transaction → budget recalculation → notification flow.

Verifies the end-to-end wiring: when an income transaction (direction="received") is
logged via POST /api/transactions, budgets are recalculated based on CategoryWeight
percentages, BudgetLimitChangeLog entries are created, and threshold notifications
fire if applicable.

Requirements: 17.1, 17.3, 17.4
"""

import math
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus, BudgetPeriodType
from app.models.budget_limit_change_log import BudgetLimitChangeLog
from app.models.category import Category
from app.models.category_weight import CategoryWeight
from app.models.notification import Notification
from app.models.transaction import Transaction, TransactionDirection
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
def test_user(test_db):
    """Create a test user."""
    user = User(id=1, timezone="UTC", current_streak=0, version=1, profile_completed=True)
    test_db.add(user)
    test_db.commit()
    return user


def _create_category(db, user_id: int, name: str) -> Category:
    """Helper to create a category."""
    cat = Category(
        user_id=user_id,
        name=name,
        usage_count=0,
        last_used_at_utc=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.flush()
    return cat


def _create_budget_with_period(
    db,
    user_id: int,
    category_id: int,
    limit: int,
    spent: int = 0,
    period_start: date = date(2024, 1, 1),
    period_end: date = date(2024, 12, 31),
) -> tuple[Budget, BudgetPeriodRecord]:
    """Helper to create a budget with an active period record."""
    budget = Budget(
        user_id=user_id,
        category_id=category_id,
        period_type=BudgetPeriodType.monthly,
        limit_smallest_unit=limit,
        currency_code="USD",
        is_active=True,
    )
    db.add(budget)
    db.flush()

    period = BudgetPeriodRecord(
        budget_id=budget.id,
        period_start=period_start,
        period_end=period_end,
        spent_smallest_unit=spent,
        status=BudgetPeriodStatus.active,
    )
    db.add(period)
    db.commit()
    db.refresh(budget)
    db.refresh(period)
    return budget, period


def _create_category_weight(db, user_id: int, category_name: str, weight_pct: float):
    """Helper to create a CategoryWeight entry."""
    cw = CategoryWeight(
        user_id=user_id,
        category_name=category_name,
        weight_percentage=Decimal(str(weight_pct)),
        is_manual_override=False,
    )
    db.add(cw)
    db.commit()
    return cw


class TestIncomeRecalculationFlow:
    """End-to-end tests for income → recalculation → notification."""

    def test_income_transaction_triggers_budget_recalculation(
        self, client, test_db, test_user
    ):
        """Req 17.1: Income transaction recalculates budget limits.

        Flow: POST income → recalculate_on_income → budget limits updated.
        """
        # Setup: category + budget + weight
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=5000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 30.0)

        # Act: Log income transaction
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100000,
                "direction": "received",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 201

        # Verify: budget limit was recalculated
        # available_balance = 100000 (received) - 0 (spent) = 100000
        # new_limit = floor(30.0 / 100 * 100000) = 30000
        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 30000

    def test_change_log_created_on_recalculation(self, client, test_db, test_user):
        """Req 17.3: Budget limit changes are logged with reason and source transaction."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=5000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 25.0)

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 80000,
                "direction": "received",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 201

        # Verify change log
        logs = test_db.query(BudgetLimitChangeLog).filter(
            BudgetLimitChangeLog.budget_id == budget.id
        ).all()
        assert len(logs) == 1
        assert logs[0].old_limit_smallest_unit == 5000
        # new_limit = floor(25.0 / 100 * 80000) = 20000
        assert logs[0].new_limit_smallest_unit == 20000
        assert "Income received" in logs[0].reason
        assert logs[0].source_transaction_id is not None

    def test_multiple_budgets_recalculated_with_varying_weights(
        self, client, test_db, test_user
    ):
        """Multiple active budgets with different weights are all recalculated."""
        # Setup: three categories with different weights
        food_cat = _create_category(test_db, test_user.id, "Food")
        transport_cat = _create_category(test_db, test_user.id, "Transport")
        entertainment_cat = _create_category(test_db, test_user.id, "Entertainment")

        budget_food, _ = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=1000, spent=0
        )
        budget_transport, _ = _create_budget_with_period(
            test_db, test_user.id, transport_cat.id, limit=1000, spent=0
        )
        budget_entertainment, _ = _create_budget_with_period(
            test_db, test_user.id, entertainment_cat.id, limit=1000, spent=0
        )

        _create_category_weight(test_db, test_user.id, "Food", 40.0)
        _create_category_weight(test_db, test_user.id, "Transport", 25.0)
        _create_category_weight(test_db, test_user.id, "Entertainment", 15.0)

        # Act: Log income
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 200000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        # Verify: each budget recalculated with its weight
        # available_balance = 200000
        test_db.refresh(budget_food)
        test_db.refresh(budget_transport)
        test_db.refresh(budget_entertainment)

        assert budget_food.limit_smallest_unit == math.floor(40.0 / 100 * 200000)  # 80000
        assert budget_transport.limit_smallest_unit == math.floor(25.0 / 100 * 200000)  # 50000
        assert budget_entertainment.limit_smallest_unit == math.floor(15.0 / 100 * 200000)  # 30000

        # Verify change logs for all three
        logs = test_db.query(BudgetLimitChangeLog).all()
        assert len(logs) == 3

    def test_threshold_notification_fires_after_recalculation(
        self, client, test_db, test_user
    ):
        """Req 17.3: Threshold notifications fire when new limits cause threshold crossings.

        If a budget has spent 8000 and the new limit is recalculated to 10000,
        that's 80% → fires budget_80 notification.
        """
        food_cat = _create_category(test_db, test_user.id, "Food")
        # Budget currently has limit=50000, spent=8000 (16% used, no threshold)
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=50000, spent=8000
        )
        _create_category_weight(test_db, test_user.id, "Food", 5.0)

        # After income of 200000:
        # available_balance = 200000
        # new_limit = floor(5.0/100 * 200000) = 10000
        # spent=8000 is 80% of new limit 10000 → should fire budget_80 notification
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 200000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        # Verify budget limit changed
        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 10000

        # Verify threshold notification fired
        notifications = test_db.query(Notification).filter(
            Notification.notification_type == "budget_80"
        ).all()
        assert len(notifications) == 1
        assert "80%" in notifications[0].body

    def test_100_percent_threshold_fires_after_recalculation(
        self, client, test_db, test_user
    ):
        """100% threshold fires when recalculated limit drops below spent amount."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        # Budget has limit=50000, spent=12000
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=50000, spent=12000
        )
        _create_category_weight(test_db, test_user.id, "Food", 5.0)

        # After income of 200000:
        # available_balance = 200000
        # new_limit = floor(5.0/100 * 200000) = 10000
        # spent=12000 is 120% of new limit 10000 → should fire both budget_80 and budget_100
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 200000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 10000

        # Both 80% and 100% notifications should fire
        notif_types = [
            n.notification_type
            for n in test_db.query(Notification).all()
        ]
        assert "budget_80" in notif_types
        assert "budget_100" in notif_types

    def test_no_recalculation_for_spent_transactions(self, client, test_db, test_user):
        """Spent (non-income) transactions should NOT trigger recalculation."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=5000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 30.0)

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 1000,
                "direction": "spent",
                "currency_code": "USD",
                "category_name": "Food",
            },
        )
        assert response.status_code == 201

        # Budget limit should NOT have changed
        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 5000

        # No change logs should exist
        logs = test_db.query(BudgetLimitChangeLog).all()
        assert len(logs) == 0

    def test_budget_without_matching_weight_is_not_recalculated(
        self, client, test_db, test_user
    ):
        """Budgets with no matching CategoryWeight entry are skipped."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=5000, spent=0
        )
        # No CategoryWeight for "Food" — budget should not change

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 5000  # unchanged

    def test_overall_budget_not_recalculated(self, client, test_db, test_user):
        """Overall budgets (category_id=None) are skipped during recalculation."""
        # Create overall budget (no category)
        budget = Budget(
            user_id=test_user.id,
            category_id=None,
            period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000,
            currency_code="USD",
            is_active=True,
        )
        test_db.add(budget)
        test_db.flush()
        period = BudgetPeriodRecord(
            budget_id=budget.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            spent_smallest_unit=0,
            status=BudgetPeriodStatus.active,
        )
        test_db.add(period)
        test_db.commit()

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 200000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 100000  # unchanged

    def test_available_balance_includes_prior_transactions(
        self, client, test_db, test_user
    ):
        """Available balance = total received - total spent across all transactions."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=1000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 50.0)

        # Pre-existing received transaction
        prior_income = Transaction(
            user_id=test_user.id,
            amount_smallest_unit=50000,
            direction=TransactionDirection.received,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date.today(),
        )
        test_db.add(prior_income)
        # Pre-existing spent transaction
        prior_expense = Transaction(
            user_id=test_user.id,
            amount_smallest_unit=10000,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date.today(),
        )
        test_db.add(prior_expense)
        test_db.commit()

        # Log new income: 30000
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 30000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        # available_balance = (50000 + 30000) - 10000 = 70000
        # new_limit = floor(50.0 / 100 * 70000) = 35000
        test_db.refresh(budget)
        assert budget.limit_smallest_unit == 35000

    def test_no_change_log_when_limit_unchanged(self, client, test_db, test_user):
        """No change log is created when new calculated limit equals current limit."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        # Set limit to exactly what recalculation would produce
        # If we receive 100000 and weight is 30%, new_limit = 30000
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=30000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 30.0)

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        # No change log because limit didn't change
        logs = test_db.query(BudgetLimitChangeLog).all()
        assert len(logs) == 0

    def test_projection_logic_works_with_dynamic_limit(self, test_db, test_user):
        """Req 17.4: Existing projection logic works with dynamically updated limits.

        After recalculation updates the limit, the projection should use the new limit.
        """
        from app.services.budget_service import calculate_budget_projection

        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id,
            limit=30000,  # dynamic limit after recalculation
            spent=6000,
            period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31),
        )

        # 10 days elapsed, 31 total days
        # daily_rate = 6000/10 = 600
        # projected = 600 * 31 = 18600 <= 30000 → on_track
        projection = calculate_budget_projection(
            budget, period, today=date(2024, 3, 11)
        )

        assert projection.status == "on_track"
        assert projection.projected_spend == 18600
        assert projection.remaining == 24000  # 30000 - 6000
        assert projection.overage == 0

    def test_change_log_reason_contains_income_amount_and_transaction_id(
        self, client, test_db, test_user
    ):
        """Req 17.3: Change log reason includes income amount and source transaction ID."""
        food_cat = _create_category(test_db, test_user.id, "Food")
        budget, period = _create_budget_with_period(
            test_db, test_user.id, food_cat.id, limit=5000, spent=0
        )
        _create_category_weight(test_db, test_user.id, "Food", 20.0)

        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 150000,
                "direction": "received",
                "currency_code": "USD",
            },
        )
        assert response.status_code == 201

        logs = test_db.query(BudgetLimitChangeLog).all()
        assert len(logs) == 1
        # Reason should contain the income amount
        assert "150000" in logs[0].reason
        # Reason should contain the transaction ID reference
        assert "transaction" in logs[0].reason.lower()
        assert logs[0].source_transaction_id is not None
