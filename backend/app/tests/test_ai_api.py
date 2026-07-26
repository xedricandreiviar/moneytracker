"""Tests for AI API endpoints.

Covers:
- POST /api/ai/recommend-budget — budget recommendation
- POST /api/ai/query — natural language data query
- GET /api/ai/coaching — pending proactive suggestions
- POST /api/ai/coaching/{id}/dismiss — dismiss a suggestion
- Rate limiting behavior
- Timeout/unavailability error handling
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus, BudgetPeriodType
from app.models.category import Category
from app.models.coaching_suggestion import CoachingSuggestion, CoachingSuggestionStatus
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.models.user_locale import UserLocale
from app.services.ai_assistant_service import (
    AIResponse,
    LLMError,
    LLMTimeoutError,
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


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the rate limiter store between tests."""
    from app.api import ai
    ai._rate_limit_store.clear()
    yield
    ai._rate_limit_store.clear()


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
    return test_user


@pytest.fixture
def test_category(test_db, test_user):
    """Create a test category."""
    category = Category(
        user_id=test_user.id,
        name="Food",
        usage_count=10,
        last_used_at_utc=datetime.utcnow(),
    )
    test_db.add(category)
    test_db.commit()
    test_db.refresh(category)
    return category


@pytest.fixture
def user_with_history(test_db, test_user_with_locale, test_category):
    """Create a user with 30 days of transaction history."""
    today = date.today()
    for i in range(30):
        txn_date = today - timedelta(days=i)
        txn = Transaction(
            user_id=test_user_with_locale.id,
            amount_smallest_unit=1500 + (i * 100),
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=test_category.id,
            transaction_date_local=txn_date,
            transaction_datetime_utc=datetime.utcnow() - timedelta(days=i),
        )
        test_db.add(txn)
    test_db.commit()
    return test_user_with_locale


@pytest.fixture
def pending_suggestion(test_db, test_user, test_category):
    """Create a pending coaching suggestion."""
    # Create a budget first
    budget = Budget(
        user_id=test_user.id,
        category_id=test_category.id,
        period_type=BudgetPeriodType.monthly,
        limit_smallest_unit=100000,
        currency_code="USD",
        is_active=True,
    )
    test_db.add(budget)
    test_db.commit()
    test_db.refresh(budget)

    suggestion = CoachingSuggestion(
        user_id=test_user.id,
        budget_id=budget.id,
        suggestion_text="Your spending is over budget by 5000. Consider reducing food expenses.",
        deviation_percentage=25.5,
        status=CoachingSuggestionStatus.pending,
        period_start=date.today() - timedelta(days=15),
        period_end=date.today() + timedelta(days=15),
        created_at_utc=datetime.utcnow(),
    )
    test_db.add(suggestion)
    test_db.commit()
    test_db.refresh(suggestion)
    return suggestion


class TestRecommendBudgetEndpoint:
    """Tests for POST /api/ai/recommend-budget."""

    @patch("app.api.ai.get_budget_recommendation")
    def test_recommend_budget_success(self, mock_recommend, client, test_user):
        """Should return successful recommendation."""
        mock_recommend.return_value = AIResponse(
            success=True,
            message="Based on your spending, I recommend a $500 monthly food budget.",
            data={
                "analysis_period": "2024-01-01 to 2024-01-30",
                "days_analyzed": 30,
                "categories_analyzed": 3,
                "total_spent": 150000,
                "total_received": 300000,
                "currency_code": "USD",
            },
        )

        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recommend" in data["message"].lower() or "$500" in data["message"]
        assert data["data"] is not None

    @patch("app.api.ai.get_budget_recommendation")
    def test_recommend_budget_insufficient_data(self, mock_recommend, client, test_user):
        """Should return informational response when insufficient data."""
        mock_recommend.return_value = AIResponse(
            success=False,
            message="Insufficient data. You need 14 days of history.",
            error_type="insufficient_data",
            data={"days_of_history": 5, "days_needed": 9},
        )

        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "insufficient_data"

    @patch("app.api.ai.get_budget_recommendation")
    def test_recommend_budget_timeout_returns_503(self, mock_recommend, client, test_user):
        """Should return 503 when LLM times out."""
        mock_recommend.return_value = AIResponse(
            success=False,
            message="The AI assistant is taking longer than expected. Please try again in a moment.",
            error_type="timeout",
        )

        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "timeout"
        assert "try again" in data["message"].lower()

    @patch("app.api.ai.get_budget_recommendation")
    def test_recommend_budget_llm_error_returns_503(self, mock_recommend, client, test_user):
        """Should return 503 when LLM is unavailable."""
        mock_recommend.return_value = AIResponse(
            success=False,
            message="The AI assistant is temporarily unavailable. Please try again later.",
            error_type="error",
        )

        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "error"

    @patch("app.api.ai.get_budget_recommendation")
    def test_recommend_budget_rate_limit_from_llm_returns_429(self, mock_recommend, client, test_user):
        """Should return 429 when LLM rate limit is hit."""
        mock_recommend.return_value = AIResponse(
            success=False,
            message="The AI assistant is currently busy. Please try again in 30 seconds.",
            error_type="rate_limit",
            data={"retry_after": 30},
        )

        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 429
        data = response.json()
        assert data["error_type"] == "rate_limit"


class TestQueryEndpoint:
    """Tests for POST /api/ai/query."""

    @patch("app.api.ai.answer_query")
    def test_query_success(self, mock_query, client, test_user):
        """Should return successful answer to a financial question."""
        mock_query.return_value = AIResponse(
            success=True,
            message="You spent $450 on food this month (Jan 1-30, 2024).",
            data={
                "analysis_period": "2024-01-01 to 2024-01-30",
                "days_of_history": 30,
                "currency_code": "USD",
            },
        )

        response = client.post(
            "/api/ai/query",
            json={"question": "How much did I spend on food this month?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] is not None

    @patch("app.api.ai.answer_query")
    def test_query_out_of_scope(self, mock_query, client, test_user):
        """Should return out-of-scope response for non-financial questions."""
        mock_query.return_value = AIResponse(
            success=False,
            message="This question doesn't appear to be about your financial data.",
            error_type="out_of_scope",
        )

        response = client.post(
            "/api/ai/query",
            json={"question": "What's the weather today?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "out_of_scope"

    @patch("app.api.ai.answer_query")
    def test_query_timeout_returns_503(self, mock_query, client, test_user):
        """Should return 503 when query times out."""
        mock_query.return_value = AIResponse(
            success=False,
            message="The response is taking too long. Please try again.",
            error_type="timeout",
        )

        response = client.post(
            "/api/ai/query",
            json={"question": "What's my average spending?"},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "timeout"
        assert "try again" in data["message"].lower()

    def test_query_empty_question_returns_422(self, client, test_user):
        """Should return 422 for empty question."""
        response = client.post(
            "/api/ai/query",
            json={"question": ""},
        )

        assert response.status_code == 422

    def test_query_missing_question_returns_422(self, client, test_user):
        """Should return 422 when question field is missing."""
        response = client.post(
            "/api/ai/query",
            json={},
        )

        assert response.status_code == 422


class TestCoachingEndpoint:
    """Tests for GET /api/ai/coaching."""

    def test_get_coaching_empty(self, client, test_user):
        """Should return empty list when no suggestions exist."""
        response = client.get("/api/ai/coaching")

        assert response.status_code == 200
        data = response.json()
        assert data["suggestions"] == []
        assert data["count"] == 0

    def test_get_coaching_with_pending_suggestions(self, client, test_user, pending_suggestion):
        """Should return pending suggestions."""
        response = client.get("/api/ai/coaching")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        suggestion = data["suggestions"][0]
        assert suggestion["id"] == pending_suggestion.id
        assert suggestion["budget_id"] == pending_suggestion.budget_id
        assert suggestion["status"] == "pending"
        assert suggestion["deviation_percentage"] == pytest.approx(25.5)
        assert "over budget" in suggestion["suggestion_text"]


class TestDismissCoachingEndpoint:
    """Tests for POST /api/ai/coaching/{id}/dismiss."""

    def test_dismiss_suggestion_success(self, client, test_user, pending_suggestion):
        """Should dismiss a pending suggestion successfully."""
        response = client.post(
            f"/api/ai/coaching/{pending_suggestion.id}/dismiss"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pending_suggestion.id
        assert data["status"] == "dismissed"
        assert data["dismissed_at_utc"] is not None

    def test_dismiss_suggestion_not_found_returns_404(self, client, test_user):
        """Should return 404 for non-existent suggestion."""
        response = client.post("/api/ai/coaching/9999/dismiss")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_dismiss_already_dismissed_returns_404(self, client, test_user, test_db, pending_suggestion):
        """Should return 404 when trying to dismiss already-dismissed suggestion."""
        # Dismiss once
        client.post(f"/api/ai/coaching/{pending_suggestion.id}/dismiss")

        # Try to dismiss again
        response = client.post(f"/api/ai/coaching/{pending_suggestion.id}/dismiss")

        assert response.status_code == 404


class TestRateLimiting:
    """Tests for AI endpoint rate limiting."""

    @patch("app.api.ai.get_budget_recommendation")
    def test_rate_limit_allows_requests_within_limit(self, mock_recommend, client, test_user):
        """Should allow requests within the rate limit."""
        mock_recommend.return_value = AIResponse(
            success=True, message="OK", data={}
        )

        # Make requests within limit
        for _ in range(10):
            response = client.post("/api/ai/recommend-budget")
            assert response.status_code == 200

    @patch("app.api.ai.get_budget_recommendation")
    def test_rate_limit_blocks_excess_requests(self, mock_recommend, client, test_user):
        """Should return 429 when rate limit is exceeded."""
        mock_recommend.return_value = AIResponse(
            success=True, message="OK", data={}
        )

        # Exhaust the rate limit
        for _ in range(10):
            client.post("/api/ai/recommend-budget")

        # 11th request should be rate limited
        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 429
        data = response.json()
        assert "too many" in data["detail"].lower()
        assert "retry_after" in data

    @patch("app.api.ai.answer_query")
    def test_rate_limit_shared_across_ai_endpoints(self, mock_query, client, test_user):
        """Rate limit is shared across all AI endpoints for the same user."""
        mock_query.return_value = AIResponse(
            success=True, message="OK", data={}
        )

        # Use up rate limit via query endpoint
        for _ in range(10):
            client.post("/api/ai/query", json={"question": "How much?"})

        # recommend-budget should also be rate limited
        response = client.post("/api/ai/recommend-budget")

        assert response.status_code == 429
