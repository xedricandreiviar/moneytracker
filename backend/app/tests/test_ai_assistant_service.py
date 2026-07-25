"""Tests for AIAssistantService.

Covers: insufficient data response, data eligibility filtering,
timeout handling, out-of-scope detection, budget recommendation generation,
and query answering.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.category import Category
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.services.ai_assistant_service import (
    AIResponse,
    CategoryAggregate,
    DataContext,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    MIN_CATEGORY_TRANSACTIONS,
    MIN_DAYS_HISTORY,
    QUERY_TIMEOUT,
    RECOMMENDATION_TIMEOUT,
    _get_days_of_history,
    _is_out_of_scope,
    answer_query,
    assemble_data_context,
    get_budget_recommendation,
)


# --- Test Helpers ---


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(
        self,
        response: str = "Mock LLM response",
        raise_timeout: bool = False,
        raise_rate_limit: bool = False,
        raise_error: bool = False,
        retry_after: Optional[int] = None,
    ):
        self.response = response
        self.raise_timeout = raise_timeout
        self.raise_rate_limit = raise_rate_limit
        self.raise_error = raise_error
        self.retry_after = retry_after
        self.last_prompt: Optional[str] = None
        self.last_timeout: Optional[float] = None
        self.call_count = 0

    def generate(self, prompt: str, timeout: float) -> str:
        self.last_prompt = prompt
        self.last_timeout = timeout
        self.call_count += 1

        if self.raise_timeout:
            raise LLMTimeoutError("Timed out")
        if self.raise_rate_limit:
            raise LLMRateLimitError(retry_after=self.retry_after)
        if self.raise_error:
            raise LLMError("API error")
        return self.response


def _create_test_session() -> Session:
    """Create an in-memory SQLite engine and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession()


def _create_user(db: Session) -> User:
    """Helper to create a test user."""
    user = User(
        timezone="UTC",
        current_streak=0,
        created_at_utc=datetime.now(timezone.utc),
        version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_category(db: Session, user_id: int, name: str) -> Category:
    """Helper to create a category."""
    cat = Category(
        user_id=user_id,
        name=name,
        usage_count=1,
        last_used_at_utc=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _create_transaction(
    db: Session,
    user_id: int,
    amount: int,
    direction: str,
    local_date: date,
    category_id: Optional[int] = None,
) -> Transaction:
    """Helper to create a transaction with a specific local date."""
    txn = Transaction(
        user_id=user_id,
        amount_smallest_unit=amount,
        direction=TransactionDirection(direction),
        currency_code="USD",
        category_id=category_id,
        transaction_datetime_utc=datetime.now(timezone.utc),
        transaction_date_local=local_date,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def _create_transactions_over_days(
    db: Session,
    user_id: int,
    category_id: int,
    num_days: int,
    amount: int = 1000,
    start_date: Optional[date] = None,
) -> None:
    """Create one transaction per day over num_days."""
    if start_date is None:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=num_days - 1)
    for i in range(num_days):
        _create_transaction(
            db, user_id, amount, "spent",
            start_date + timedelta(days=i),
            category_id,
        )


# --- Tests for insufficient data handling (Req 9.3) ---


class TestInsufficientData:
    """Tests for insufficient data detection and responses."""

    def test_no_transactions_returns_insufficient_data(self):
        """User with zero transactions should get insufficient data response."""
        db = _create_test_session()
        user = _create_user(db)
        mock_llm = MockLLMClient()

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "insufficient_data"
        assert "0 days" in result.message
        assert str(MIN_DAYS_HISTORY) in result.message
        assert mock_llm.call_count == 0
        db.close()

    def test_fewer_than_14_days_returns_days_needed(self):
        """User with < 14 days should get specific days needed."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient()

        # Create 10 days of history
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=9)
        _create_transactions_over_days(db, user.id, food.id, 10, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "insufficient_data"
        assert result.data["days_of_history"] == 10
        assert result.data["days_needed"] == 4
        assert "4 more day" in result.message
        assert mock_llm.call_count == 0
        db.close()

    def test_exactly_14_days_proceeds(self):
        """User with exactly 14 days should proceed to LLM call."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="Budget recommendation response")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=13)
        _create_transactions_over_days(db, user.id, food.id, 14, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        # Should have enough days but might fail on eligible categories check
        # With 14 transactions in one category, it should pass
        assert result.success is True
        assert mock_llm.call_count == 1
        db.close()

    def test_query_with_zero_history_returns_insufficient(self):
        """answer_query with no data should return insufficient data."""
        db = _create_test_session()
        user = _create_user(db)
        mock_llm = MockLLMClient()

        result = answer_query(db, user.id, "How much did I spend?", llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "insufficient_data"
        assert mock_llm.call_count == 0
        db.close()


# --- Tests for data eligibility filtering (Req 9.4) ---


class TestDataEligibilityFiltering:
    """Tests for category eligibility (3+ transactions required)."""

    def test_categories_with_fewer_than_3_transactions_excluded(self):
        """Categories with < 3 transactions should not be in eligible list."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        transport = _create_category(db, user.id, "Transport")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)

        # Food: 5 transactions (eligible)
        _create_transactions_over_days(db, user.id, food.id, 5, start_date=start)
        # Transport: 2 transactions (NOT eligible)
        _create_transaction(db, user.id, 500, "spent", start, transport.id)
        _create_transaction(db, user.id, 600, "spent", start + timedelta(days=1), transport.id)

        context = assemble_data_context(db, user.id)

        eligible_names = [c.category_name for c in context.eligible_categories]
        assert "Food" in eligible_names
        assert "Transport" not in eligible_names
        db.close()

    def test_exactly_3_transactions_is_eligible(self):
        """Category with exactly 3 transactions should be eligible."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 3, start_date=start)

        context = assemble_data_context(db, user.id)

        eligible_names = [c.category_name for c in context.eligible_categories]
        assert "Food" in eligible_names
        db.close()

    def test_no_eligible_categories_returns_error(self):
        """If all categories have < 3 transactions, return error."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        transport = _create_category(db, user.id, "Transport")
        mock_llm = MockLLMClient()

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=20)

        # Spread transactions over 14+ days but each category has only 2
        _create_transaction(db, user.id, 1000, "spent", start, food.id)
        _create_transaction(db, user.id, 1000, "spent", start + timedelta(days=7), food.id)
        _create_transaction(db, user.id, 500, "spent", start + timedelta(days=10), transport.id)
        _create_transaction(db, user.id, 500, "spent", start + timedelta(days=20), transport.id)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "insufficient_data"
        assert "3 transactions" in result.message
        assert mock_llm.call_count == 0
        db.close()

    def test_data_context_never_includes_notes(self):
        """Data context should aggregate by category, never include notes."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")

        today = datetime.now(timezone.utc).date()
        # Create transactions with notes that should NOT appear in context
        for i in range(5):
            txn = Transaction(
                user_id=user.id,
                amount_smallest_unit=1000,
                direction=TransactionDirection.spent,
                currency_code="USD",
                category_id=food.id,
                note=f"Secret note {i}",
                transaction_datetime_utc=datetime.now(timezone.utc),
                transaction_date_local=today - timedelta(days=i),
            )
            db.add(txn)
        db.commit()

        context = assemble_data_context(db, user.id)

        # Verify notes are not in the context
        for cat in context.category_aggregates:
            assert not hasattr(cat, "notes")
        db.close()


# --- Tests for timeout handling (Req 9.5, 9.6, 11.4, 11.5) ---


class TestTimeoutHandling:
    """Tests for LLM timeout and error handling."""

    def test_recommendation_timeout_returns_error(self):
        """LLM timeout during recommendation should return timeout error."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(raise_timeout=True)

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 30, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "timeout"
        assert "try again" in result.message.lower()
        db.close()

    def test_query_timeout_returns_error(self):
        """LLM timeout during query should return timeout error."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(raise_timeout=True)

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)

        result = answer_query(db, user.id, "How much did I spend on food?", llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "timeout"
        assert "try again" in result.message.lower()
        db.close()

    def test_recommendation_uses_15s_timeout(self):
        """Recommendation should use 15-second timeout."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="OK")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 30, start_date=start)

        get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert mock_llm.last_timeout == RECOMMENDATION_TIMEOUT
        assert mock_llm.last_timeout == 15
        db.close()

    def test_query_uses_10s_timeout(self):
        """Query should use 10-second timeout."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="OK")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)

        answer_query(db, user.id, "How much did I spend?", llm_client=mock_llm)

        assert mock_llm.last_timeout == QUERY_TIMEOUT
        assert mock_llm.last_timeout == 10
        db.close()

    def test_rate_limit_returns_retry_info(self):
        """Rate limit error should include retry_after info."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(raise_rate_limit=True, retry_after=30)

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 30, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "rate_limit"
        assert result.data["retry_after"] == 30
        assert "30 seconds" in result.message
        db.close()

    def test_general_llm_error_returns_unavailable(self):
        """General LLM error should return unavailable message."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(raise_error=True)

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 30, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is False
        assert result.error_type == "error"
        assert "unavailable" in result.message.lower()
        db.close()


# --- Tests for out-of-scope detection (Req 11.6) ---


class TestOutOfScopeDetection:
    """Tests for detecting non-financial queries."""

    def test_weather_question_is_out_of_scope(self):
        """Weather question should be detected as out of scope."""
        assert _is_out_of_scope("What's the weather like today?") is True

    def test_recipe_question_is_out_of_scope(self):
        """Recipe question should be detected as out of scope."""
        assert _is_out_of_scope("Give me a recipe for chocolate cake") is True

    def test_spending_question_is_in_scope(self):
        """Spending question should NOT be out of scope."""
        assert _is_out_of_scope("How much did I spend on food?") is False

    def test_budget_question_is_in_scope(self):
        """Budget question should NOT be out of scope."""
        assert _is_out_of_scope("What's my budget status?") is False

    def test_income_question_is_in_scope(self):
        """Income question should NOT be out of scope."""
        assert _is_out_of_scope("What's my total income this month?") is False

    def test_ambiguous_question_defaults_to_in_scope(self):
        """Question without clear signals should default to in-scope."""
        assert _is_out_of_scope("What are my totals?") is False

    def test_out_of_scope_response_includes_examples(self):
        """Out-of-scope answer should include example financial questions."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient()

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)

        result = answer_query(
            db, user.id, "What's the weather forecast?", llm_client=mock_llm
        )

        assert result.success is False
        assert result.error_type == "out_of_scope"
        assert "How much did I spend" in result.message
        assert mock_llm.call_count == 0
        db.close()

    def test_financial_keyword_overrides_non_financial(self):
        """Financial keywords should override non-financial keywords."""
        # "How much did I spend on exercise?" has both "exercise" and "spend"
        assert _is_out_of_scope("How much did I spend on exercise?") is False


# --- Tests for budget recommendation generation (Req 9.1, 9.2) ---


class TestBudgetRecommendation:
    """Tests for successful budget recommendation generation."""

    def test_successful_recommendation(self):
        """Valid data should produce successful recommendation."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        transport = _create_category(db, user.id, "Transport")
        mock_llm = MockLLMClient(
            response="I recommend a $200/month food budget based on your average."
        )

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 15, start_date=start)
        _create_transactions_over_days(
            db, user.id, transport.id, 5,
            start_date=start + timedelta(days=5), amount=500,
        )

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.success is True
        assert "recommend" in result.message.lower()
        assert result.data["categories_analyzed"] >= 1
        assert result.data["currency_code"] == "USD"
        db.close()

    def test_prompt_includes_category_data(self):
        """Recommendation prompt should include category aggregates."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="Budget recommendation")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        # Create 15 transactions to ensure 14+ days of history with 3+ per category
        _create_transactions_over_days(db, user.id, food.id, 15, start_date=start)

        get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert mock_llm.last_prompt is not None
        assert "Food" in mock_llm.last_prompt
        assert "spent=" in mock_llm.last_prompt
        assert "transactions=" in mock_llm.last_prompt
        db.close()

    def test_recommendation_response_includes_metadata(self):
        """Response should include analysis metadata."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="Budget advice")

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        _create_transactions_over_days(db, user.id, food.id, 15, start_date=start)

        result = get_budget_recommendation(db, user.id, llm_client=mock_llm)

        assert result.data is not None
        assert "analysis_period" in result.data
        assert "days_analyzed" in result.data
        assert "total_spent" in result.data
        assert "total_received" in result.data
        db.close()


# --- Tests for query answering (Req 11.1, 11.2, 11.3) ---


class TestAnswerQuery:
    """Tests for conversational data query answering."""

    def test_successful_query_answer(self):
        """Valid question with data should produce successful answer."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(
            response="You spent $150 on food in the last 30 days."
        )

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=20)
        _create_transactions_over_days(db, user.id, food.id, 20, start_date=start)

        result = answer_query(
            db, user.id, "How much did I spend on food?", llm_client=mock_llm
        )

        assert result.success is True
        assert "$150" in result.message
        assert result.data["currency_code"] == "USD"
        db.close()

    def test_query_with_limited_data_includes_note(self):
        """Query with < 14 days data should include limitation note."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="You spent $50 on food.")

        today = datetime.now(timezone.utc).date()
        # Only 5 days of history
        _create_transactions_over_days(db, user.id, food.id, 5, start_date=today - timedelta(days=4))

        result = answer_query(
            db, user.id, "How much did I spend on food?", llm_client=mock_llm
        )

        assert result.success is True
        assert "more days" in result.message
        db.close()

    def test_query_prompt_includes_question(self):
        """Query prompt should include the user's question."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        mock_llm = MockLLMClient(response="Answer")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)

        answer_query(
            db, user.id, "What is my biggest expense category?", llm_client=mock_llm
        )

        assert "What is my biggest expense category?" in mock_llm.last_prompt
        db.close()

    def test_query_prompt_includes_category_breakdown(self):
        """Query prompt should include category data."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        transport = _create_category(db, user.id, "Transport")
        mock_llm = MockLLMClient(response="Answer")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)
        _create_transaction(db, user.id, 500, "spent", today, transport.id)

        answer_query(
            db, user.id, "Which category has the highest spending?",
            llm_client=mock_llm,
        )

        assert "Food" in mock_llm.last_prompt
        assert "Transport" in mock_llm.last_prompt
        db.close()


# --- Tests for data context assembly ---


class TestDataContextAssembly:
    """Tests for the assemble_data_context function."""

    def test_aggregates_by_category(self):
        """Should aggregate transactions by category."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)
        _create_transaction(db, user.id, 2000, "spent", today - timedelta(days=1), food.id)
        _create_transaction(db, user.id, 5000, "received", today, food.id)

        context = assemble_data_context(db, user.id)

        assert len(context.category_aggregates) == 1
        cat = context.category_aggregates[0]
        assert cat.category_name == "Food"
        assert cat.total_spent == 3000
        assert cat.total_received == 5000
        assert cat.transaction_count == 3
        db.close()

    def test_computes_average_transaction(self):
        """Should compute average transaction amount for spent."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today, food.id)
        _create_transaction(db, user.id, 3000, "spent", today - timedelta(days=1), food.id)

        context = assemble_data_context(db, user.id)

        cat = context.category_aggregates[0]
        # Average of 1000 and 3000 = 2000
        assert cat.average_transaction == 2000
        db.close()

    def test_sorts_by_total_spent_descending(self):
        """Categories should be sorted by total spent descending."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")
        rent = _create_category(db, user.id, "Rent")
        fun = _create_category(db, user.id, "Fun")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 500, "spent", today, food.id)
        _create_transaction(db, user.id, 10000, "spent", today, rent.id)
        _create_transaction(db, user.id, 200, "spent", today, fun.id)

        context = assemble_data_context(db, user.id)

        names = [c.category_name for c in context.category_aggregates]
        assert names == ["Rent", "Food", "Fun"]
        db.close()

    def test_days_of_history_calculation(self):
        """Should correctly calculate days of history."""
        db = _create_test_session()
        user = _create_user(db)
        food = _create_category(db, user.id, "Food")

        today = datetime.now(timezone.utc).date()
        _create_transaction(db, user.id, 1000, "spent", today - timedelta(days=20), food.id)
        _create_transaction(db, user.id, 1000, "spent", today, food.id)

        days = _get_days_of_history(db, user.id)
        assert days == 21  # 20 days apart + 1 (inclusive)
        db.close()

    def test_empty_history_returns_zero_days(self):
        """No transactions should return 0 days of history."""
        db = _create_test_session()
        user = _create_user(db)

        days = _get_days_of_history(db, user.id)
        assert days == 0
        db.close()
