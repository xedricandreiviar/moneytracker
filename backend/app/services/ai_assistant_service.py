"""AIAssistantService for budget recommendations and conversational data queries.

Provides AI-powered features:
- Budget recommendations based on historical spending (30-90 days)
- Natural language data queries answered from transaction history
- Data context assembly that aggregates by category (never sends raw notes to LLM)
- LLM client abstraction for testability

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import Transaction, TransactionDirection

logger = logging.getLogger(__name__)

# Timeout configuration (seconds)
RECOMMENDATION_TIMEOUT = 15
QUERY_TIMEOUT = 10

# Data eligibility thresholds
MIN_DAYS_HISTORY = 14
MIN_CATEGORY_TRANSACTIONS = 3

# Analysis window
ANALYSIS_DAYS_MIN = 30
ANALYSIS_DAYS_MAX = 90

# Out-of-scope keywords that indicate non-financial queries
NON_FINANCIAL_KEYWORDS = [
    "weather", "news", "sports", "recipe", "movie", "music", "game",
    "joke", "poem", "story", "translate", "directions", "map",
    "health", "medical", "exercise", "workout", "diet",
    "politics", "election", "celebrity", "horoscope",
]

EXAMPLE_FINANCIAL_QUESTIONS = [
    "How much did I spend on food this month?",
    "What's my average weekly spending?",
    "Which category has the highest spending?",
    "How does my spending this month compare to last month?",
    "What's my income vs expenses ratio?",
]


@dataclass
class CategoryAggregate:
    """Aggregated spending data for a single category."""

    category_name: str
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    transaction_count: int
    average_transaction: int  # smallest currency unit (spent only)
    first_transaction_date: date
    last_transaction_date: date


@dataclass
class DataContext:
    """Assembled data context for LLM prompts. Never includes raw notes."""

    user_id: int
    days_of_history: int
    analysis_start: date
    analysis_end: date
    total_spent: int  # smallest currency unit
    total_received: int  # smallest currency unit
    currency_code: str
    category_aggregates: list[CategoryAggregate] = field(default_factory=list)
    eligible_categories: list[CategoryAggregate] = field(default_factory=list)


@dataclass
class AIResponse:
    """Response from AI assistant operations."""

    success: bool
    message: str
    data: Optional[dict] = None
    error_type: Optional[str] = None  # "insufficient_data", "timeout", "rate_limit", "out_of_scope", "error"


class LLMClient(Protocol):
    """Protocol for LLM client abstraction. Implementations can be swapped for testing."""

    def generate(self, prompt: str, timeout: float) -> str:
        """Send a prompt to the LLM and return the response text.

        Args:
            prompt: The fully assembled prompt with data context.
            timeout: Maximum time in seconds to wait for response.

        Returns:
            The LLM response text.

        Raises:
            LLMTimeoutError: If the request exceeds the timeout.
            LLMRateLimitError: If rate limit is exceeded.
            LLMError: For other LLM API errors.
        """
        ...


class LLMTimeoutError(Exception):
    """Raised when LLM API call exceeds timeout."""
    pass


class LLMRateLimitError(Exception):
    """Raised when LLM API rate limit is exceeded."""

    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after: {retry_after}s")


class LLMError(Exception):
    """Raised for general LLM API errors."""
    pass


class DefaultLLMClient:
    """Default LLM client that calls an external API.

    Configurable via environment variables:
    - LLM_API_KEY: API key for authentication
    - LLM_API_ENDPOINT: Base URL for the LLM API
    - LLM_MODEL: Model name to use (default: gpt-4o-mini)
    """

    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.endpoint = os.environ.get("LLM_API_ENDPOINT", "https://api.openai.com/v1/chat/completions")
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    def generate(self, prompt: str, timeout: float) -> str:
        """Send prompt to LLM API with timeout handling.

        Args:
            prompt: The fully assembled prompt.
            timeout: Maximum seconds to wait.

        Returns:
            LLM response text.

        Raises:
            LLMTimeoutError: On timeout.
            LLMRateLimitError: On rate limit (429).
            LLMError: On other errors.
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a personal finance assistant. Provide specific, data-driven advice based on the user's actual financial data provided in the context. Always reference specific numbers and time periods."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(self.endpoint, json=payload, headers=headers)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise LLMRateLimitError(
                    retry_after=int(retry_after) if retry_after else None
                )

            if response.status_code != 200:
                raise LLMError(f"LLM API returned status {response.status_code}")

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except httpx.TimeoutException:
            raise LLMTimeoutError(f"LLM API timed out after {timeout}s")
        except (LLMTimeoutError, LLMRateLimitError, LLMError):
            raise
        except Exception as e:
            raise LLMError(f"LLM API error: {str(e)}")


def _get_transaction_date_range(db: Session, user_id: int) -> Optional[tuple[date, date]]:
    """Get the earliest and latest transaction dates for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        Tuple of (earliest_date, latest_date) or None if no transactions exist.
    """
    result = (
        db.query(
            func.min(Transaction.transaction_date_local),
            func.max(Transaction.transaction_date_local),
        )
        .filter(Transaction.user_id == user_id)
        .first()
    )

    if result and result[0] is not None and result[1] is not None:
        return (result[0], result[1])
    return None


def _get_days_of_history(db: Session, user_id: int) -> int:
    """Calculate the number of days of transaction history for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        Number of days between first and last transaction (inclusive), or 0.
    """
    date_range = _get_transaction_date_range(db, user_id)
    if date_range is None:
        return 0
    earliest, latest = date_range
    return (latest - earliest).days + 1


def assemble_data_context(
    db: Session,
    user_id: int,
    days_back: Optional[int] = None,
) -> DataContext:
    """Assemble aggregated data context for LLM prompts.

    Aggregates transactions by category. Never includes raw transaction notes.
    This ensures user privacy while providing the LLM with useful financial patterns.

    Args:
        db: Database session.
        user_id: The user's ID.
        days_back: Number of days to look back (default: up to 90 days, min 30).

    Returns:
        DataContext with aggregated category-level data.
    """
    today = datetime.now(timezone.utc).date()

    # Determine analysis window
    if days_back is None:
        # Use up to 90 days, but at least 30
        date_range = _get_transaction_date_range(db, user_id)
        if date_range:
            available_days = (today - date_range[0]).days + 1
            days_back = min(available_days, ANALYSIS_DAYS_MAX)
            days_back = max(days_back, ANALYSIS_DAYS_MIN)
        else:
            days_back = ANALYSIS_DAYS_MIN

    analysis_start = today - timedelta(days=days_back - 1)
    analysis_end = today

    # Get total days of history
    days_of_history = _get_days_of_history(db, user_id)

    # Get overall totals
    overall_totals = (
        db.query(
            Transaction.direction,
            func.sum(Transaction.amount_smallest_unit).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date_local >= analysis_start,
            Transaction.transaction_date_local <= analysis_end,
        )
        .group_by(Transaction.direction)
        .all()
    )

    total_spent = 0
    total_received = 0
    for direction, total in overall_totals:
        if direction == TransactionDirection.spent:
            total_spent = total or 0
        else:
            total_received = total or 0

    # Get currency code from most recent transaction
    latest_txn = (
        db.query(Transaction.currency_code)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_datetime_utc.desc())
        .first()
    )
    currency_code = latest_txn[0] if latest_txn else "USD"

    # Get category aggregates
    category_data = (
        db.query(
            Category.name,
            Transaction.direction,
            func.sum(Transaction.amount_smallest_unit).label("total"),
            func.count(Transaction.id).label("txn_count"),
            func.min(Transaction.transaction_date_local).label("first_date"),
            func.max(Transaction.transaction_date_local).label("last_date"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date_local >= analysis_start,
            Transaction.transaction_date_local <= analysis_end,
        )
        .group_by(Category.name, Transaction.direction)
        .all()
    )

    # Assemble category aggregates
    category_map: dict[str, dict] = {}
    for cat_name, direction, total, count, first_dt, last_dt in category_data:
        if cat_name not in category_map:
            category_map[cat_name] = {
                "total_spent": 0,
                "total_received": 0,
                "spent_count": 0,
                "received_count": 0,
                "first_date": first_dt,
                "last_date": last_dt,
            }

        if direction == TransactionDirection.spent:
            category_map[cat_name]["total_spent"] = total or 0
            category_map[cat_name]["spent_count"] = count
        else:
            category_map[cat_name]["total_received"] = total or 0
            category_map[cat_name]["received_count"] = count

        # Track overall date range per category
        if first_dt and (first_dt < category_map[cat_name]["first_date"]):
            category_map[cat_name]["first_date"] = first_dt
        if last_dt and (last_dt > category_map[cat_name]["last_date"]):
            category_map[cat_name]["last_date"] = last_dt

    category_aggregates: list[CategoryAggregate] = []
    for cat_name, data in category_map.items():
        txn_count = data["spent_count"] + data["received_count"]
        avg_spent = (
            data["total_spent"] // data["spent_count"]
            if data["spent_count"] > 0
            else 0
        )
        category_aggregates.append(
            CategoryAggregate(
                category_name=cat_name,
                total_spent=data["total_spent"],
                total_received=data["total_received"],
                transaction_count=txn_count,
                average_transaction=avg_spent,
                first_transaction_date=data["first_date"],
                last_transaction_date=data["last_date"],
            )
        )

    # Sort by total spent descending
    category_aggregates.sort(key=lambda c: c.total_spent, reverse=True)

    # Filter eligible categories (3+ transactions) for recommendations
    eligible_categories = [
        ca for ca in category_aggregates
        if ca.transaction_count >= MIN_CATEGORY_TRANSACTIONS
    ]

    return DataContext(
        user_id=user_id,
        days_of_history=days_of_history,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        total_spent=total_spent,
        total_received=total_received,
        currency_code=currency_code,
        category_aggregates=category_aggregates,
        eligible_categories=eligible_categories,
    )


def _build_recommendation_prompt(context: DataContext) -> str:
    """Build a structured prompt for budget recommendations.

    Includes aggregated category data, income totals, and analysis period.
    Never includes raw transaction notes.

    Args:
        context: Assembled data context.

    Returns:
        Formatted prompt string.
    """
    lines = [
        "Based on the following financial data, provide budget recommendations for each eligible category.",
        "",
        f"Analysis period: {context.analysis_start} to {context.analysis_end} ({context.days_of_history} days of history)",
        f"Currency: {context.currency_code}",
        f"Total spent: {context.total_spent} (in smallest currency unit)",
        f"Total received: {context.total_received} (in smallest currency unit)",
        "",
        "Eligible categories (3+ transactions in analysis period):",
    ]

    for cat in context.eligible_categories:
        lines.append(
            f"- {cat.category_name}: "
            f"spent={cat.total_spent}, "
            f"transactions={cat.transaction_count}, "
            f"avg_per_transaction={cat.average_transaction}, "
            f"period={cat.first_transaction_date} to {cat.last_transaction_date}"
        )

    lines.extend([
        "",
        "Instructions:",
        "1. For each eligible category, recommend a realistic monthly budget amount (in smallest currency unit).",
        "2. Explain your reasoning referencing the specific spending averages and income.",
        "3. Consider the user's income when recommending budgets.",
        "4. Format your response as actionable advice with specific numbers.",
    ])

    return "\n".join(lines)


def _build_query_prompt(context: DataContext, question: str) -> str:
    """Build a structured prompt for answering a user's data query.

    Includes relevant aggregated data and the user's question.

    Args:
        context: Assembled data context.
        question: The user's natural language question.

    Returns:
        Formatted prompt string.
    """
    lines = [
        "Answer the following question about the user's financial data.",
        "Use ONLY the data provided below. Include specific numbers and time ranges in your answer.",
        "If the data is insufficient to answer, state what data is missing.",
        "",
        f"Analysis period: {context.analysis_start} to {context.analysis_end}",
        f"Days of history: {context.days_of_history}",
        f"Currency: {context.currency_code}",
        f"Total spent: {context.total_spent} (in smallest currency unit)",
        f"Total received: {context.total_received} (in smallest currency unit)",
        "",
        "Category breakdown:",
    ]

    for cat in context.category_aggregates:
        lines.append(
            f"- {cat.category_name}: "
            f"spent={cat.total_spent}, "
            f"received={cat.total_received}, "
            f"transactions={cat.transaction_count}, "
            f"avg_spent_per_txn={cat.average_transaction}"
        )

    if not context.category_aggregates:
        lines.append("- No categorized transactions available.")

    lines.extend([
        "",
        f"User's question: {question}",
        "",
        "Provide a clear, specific answer with numbers and the time range analyzed.",
    ])

    return "\n".join(lines)


def _is_out_of_scope(question: str) -> bool:
    """Determine if a question is not related to financial data.

    Checks against known non-financial keywords. A question is out of scope
    if it contains non-financial keywords without any financial context.

    Args:
        question: The user's question.

    Returns:
        True if the question is out of scope for financial data queries.
    """
    question_lower = question.lower()

    # Financial keywords that indicate the question IS in scope
    financial_keywords = [
        "spend", "spent", "income", "earn", "budget", "money", "cost",
        "expense", "save", "saving", "pay", "payment", "transaction",
        "category", "month", "week", "average", "total", "balance",
        "receipt", "bill", "subscription", "rent", "food", "transport",
        "salary", "wage", "financial", "finance",
    ]

    # Check if any financial keyword is present
    has_financial_context = any(kw in question_lower for kw in financial_keywords)
    if has_financial_context:
        return False

    # Check if non-financial keywords are present
    has_non_financial = any(kw in question_lower for kw in NON_FINANCIAL_KEYWORDS)
    if has_non_financial:
        return True

    # If no clear signals, assume it could be financial (let LLM decide)
    return False


def get_budget_recommendation(
    db: Session,
    user_id: int,
    llm_client: Optional[LLMClient] = None,
) -> AIResponse:
    """Generate AI budget recommendations based on spending history.

    Analyzes 30-90 days of history. Requires at least 14 days of data.
    Only includes categories with 3+ transactions.

    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6

    Args:
        db: Database session.
        user_id: The user's ID.
        llm_client: Optional LLM client (uses DefaultLLMClient if not provided).

    Returns:
        AIResponse with recommendation or error information.
    """
    # Check data eligibility (Req 9.3)
    days_of_history = _get_days_of_history(db, user_id)

    if days_of_history < MIN_DAYS_HISTORY:
        days_needed = MIN_DAYS_HISTORY - days_of_history
        return AIResponse(
            success=False,
            message=(
                f"Insufficient data for budget recommendations. "
                f"You have {days_of_history} days of history, but at least "
                f"{MIN_DAYS_HISTORY} days are required. "
                f"Please log transactions for {days_needed} more day(s)."
            ),
            error_type="insufficient_data",
            data={"days_of_history": days_of_history, "days_needed": days_needed},
        )

    # Assemble data context (Req 9.1 - never send raw notes)
    context = assemble_data_context(db, user_id)

    # Check if there are eligible categories (Req 9.4)
    if not context.eligible_categories:
        return AIResponse(
            success=False,
            message=(
                "Not enough categorized transactions for recommendations. "
                "Each category needs at least 3 transactions. "
                "Keep logging and categorizing your transactions."
            ),
            error_type="insufficient_data",
            data={"days_of_history": days_of_history, "eligible_categories": 0},
        )

    # Build prompt and call LLM (Req 9.2)
    prompt = _build_recommendation_prompt(context)

    if llm_client is None:
        llm_client = DefaultLLMClient()

    try:
        response_text = llm_client.generate(prompt, timeout=RECOMMENDATION_TIMEOUT)

        return AIResponse(
            success=True,
            message=response_text,
            data={
                "analysis_period": f"{context.analysis_start} to {context.analysis_end}",
                "days_analyzed": context.days_of_history,
                "categories_analyzed": len(context.eligible_categories),
                "total_spent": context.total_spent,
                "total_received": context.total_received,
                "currency_code": context.currency_code,
            },
        )

    except LLMTimeoutError:
        # Req 9.5, 9.6: Handle timeout
        logger.warning(f"LLM timeout for budget recommendation (user_id={user_id})")
        return AIResponse(
            success=False,
            message=(
                "The AI assistant is taking longer than expected. "
                "Please try again in a moment."
            ),
            error_type="timeout",
        )

    except LLMRateLimitError as e:
        logger.warning(f"LLM rate limit for budget recommendation (user_id={user_id})")
        return AIResponse(
            success=False,
            message=(
                "The AI assistant is currently busy. "
                f"Please try again{f' in {e.retry_after} seconds' if e.retry_after else ' shortly'}."
            ),
            error_type="rate_limit",
            data={"retry_after": e.retry_after},
        )

    except LLMError as e:
        # Req 9.6: Handle general errors
        logger.error(f"LLM error for budget recommendation (user_id={user_id}): {e}")
        return AIResponse(
            success=False,
            message=(
                "The AI assistant is temporarily unavailable. "
                "Please try again later."
            ),
            error_type="error",
        )


def answer_query(
    db: Session,
    user_id: int,
    question: str,
    llm_client: Optional[LLMClient] = None,
) -> AIResponse:
    """Answer a natural language question about the user's financial data.

    Assembles relevant data context, checks for out-of-scope questions,
    queries the LLM, and returns a response with specific numbers and time ranges.

    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6

    Args:
        db: Database session.
        user_id: The user's ID.
        question: The user's natural language question.
        llm_client: Optional LLM client (uses DefaultLLMClient if not provided).

    Returns:
        AIResponse with answer or error information.
    """
    # Req 11.6: Check for out-of-scope questions
    if _is_out_of_scope(question):
        return AIResponse(
            success=False,
            message=(
                "This question doesn't appear to be about your financial data. "
                "I can help with questions like:\n"
                + "\n".join(f"• {q}" for q in EXAMPLE_FINANCIAL_QUESTIONS)
            ),
            error_type="out_of_scope",
        )

    # Check if user has any data
    days_of_history = _get_days_of_history(db, user_id)
    if days_of_history == 0:
        return AIResponse(
            success=False,
            message=(
                "You don't have any transaction history yet. "
                "Start logging transactions and I'll be able to answer questions about your finances."
            ),
            error_type="insufficient_data",
            data={"days_of_history": 0},
        )

    # Assemble data context
    context = assemble_data_context(db, user_id)

    # Req 11.3: If data is very limited, note what's missing
    if days_of_history < MIN_DAYS_HISTORY:
        days_needed = MIN_DAYS_HISTORY - days_of_history
        # Still attempt to answer with available data but note limitation
        limitation_note = (
            f"\nNote: You have {days_of_history} days of history. "
            f"For more accurate answers, {days_needed} more days of data would help."
        )
    else:
        limitation_note = ""

    # Build prompt and call LLM
    prompt = _build_query_prompt(context, question)

    if llm_client is None:
        llm_client = DefaultLLMClient()

    try:
        response_text = llm_client.generate(prompt, timeout=QUERY_TIMEOUT)

        message = response_text + limitation_note

        return AIResponse(
            success=True,
            message=message,
            data={
                "analysis_period": f"{context.analysis_start} to {context.analysis_end}",
                "days_of_history": days_of_history,
                "currency_code": context.currency_code,
            },
        )

    except LLMTimeoutError:
        # Req 11.4, 11.5: Handle timeout
        logger.warning(f"LLM timeout for query (user_id={user_id})")
        return AIResponse(
            success=False,
            message=(
                "The response is taking too long. "
                "Please try again."
            ),
            error_type="timeout",
        )

    except LLMRateLimitError as e:
        logger.warning(f"LLM rate limit for query (user_id={user_id})")
        return AIResponse(
            success=False,
            message=(
                "The AI assistant is currently busy. "
                f"Please try again{f' in {e.retry_after} seconds' if e.retry_after else ' shortly'}."
            ),
            error_type="rate_limit",
            data={"retry_after": e.retry_after},
        )

    except LLMError as e:
        # Req 11.5: Handle general errors
        logger.error(f"LLM error for query (user_id={user_id}): {e}")
        return AIResponse(
            success=False,
            message=(
                "The AI assistant is temporarily unavailable. "
                "Please try again later."
            ),
            error_type="error",
        )
