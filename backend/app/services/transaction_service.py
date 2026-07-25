"""TransactionService for creating, querying, and managing transactions.

Handles validation, persistence with retry logic, category frequency queries,
and category suggestion logic.
"""

import json
import time
import functools
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.category_override import CategoryOverride
from app.models.transaction import Transaction, TransactionDirection

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [0.5, 1.0, 2.0]  # Exponential backoff, max 2s


class TransactionValidationError(Exception):
    """Raised when transaction input fails validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def with_db_retry(func_to_wrap):
    """Decorator that retries DB operations up to 3 times with exponential backoff.

    Retry delays: [0.5s, 1.0s, 2.0s]
    On exhaustion, raises the original exception.
    """

    @functools.wraps(func_to_wrap)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func_to_wrap(*args, **kwargs)
            except OperationalError as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"DB operation failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"DB operation failed after {MAX_RETRIES} attempts: {e}"
                    )
        raise last_exception

    return wrapper


def _validate_transaction_input(
    amount_smallest_unit: int,
    direction: str,
    currency_code: str,
    note: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> None:
    """Validate transaction input fields.

    Args:
        amount_smallest_unit: Must be a positive integer.
        direction: Must be "spent" or "received".
        currency_code: Must be a 3-character ISO 4217 code.
        note: If provided, max 200 characters.
        tags: If provided, max 10 items.

    Raises:
        TransactionValidationError: If any validation fails.
    """
    if not isinstance(amount_smallest_unit, int) or amount_smallest_unit <= 0:
        raise TransactionValidationError(
            "amount", "Amount must be a positive integer in smallest currency unit."
        )

    if direction not in ("spent", "received"):
        raise TransactionValidationError(
            "direction", "Direction must be 'spent' or 'received'."
        )

    if not currency_code or len(currency_code) != 3:
        raise TransactionValidationError(
            "currency_code", "Currency code must be a 3-character ISO 4217 code."
        )

    if note is not None and len(note) > 200:
        raise TransactionValidationError(
            "note", "Note must be at most 200 characters."
        )

    if tags is not None and len(tags) > 10:
        raise TransactionValidationError(
            "tags", "Maximum 10 tags allowed."
        )


def _find_or_create_category(
    db: Session, user_id: int, category_name: str
) -> Category:
    """Find an existing category by name for the user, or create a new one.

    Increments usage_count and updates last_used_at_utc.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_name: The category name to find or create.

    Returns:
        The Category instance (existing or newly created).
    """
    category = (
        db.query(Category)
        .filter(Category.user_id == user_id, Category.name == category_name)
        .first()
    )

    if category is None:
        category = Category(
            user_id=user_id,
            name=category_name,
            usage_count=1,
            last_used_at_utc=datetime.now(timezone.utc),
        )
        db.add(category)
    else:
        category.usage_count += 1
        category.last_used_at_utc = datetime.now(timezone.utc)

    return category


@with_db_retry
def create_transaction(
    db: Session,
    user_id: int,
    amount_smallest_unit: int,
    direction: str,
    currency_code: str,
    category_name: Optional[str] = None,
    note: Optional[str] = None,
    payment_method: Optional[str] = None,
    tags: Optional[list[str]] = None,
    user_timezone: str = "UTC",
) -> Transaction:
    """Create and persist a new transaction.

    Validates inputs, finds or creates category, assigns timestamps,
    and persists with retry logic.

    Args:
        db: Database session.
        user_id: The user's ID.
        amount_smallest_unit: Positive integer amount in smallest currency unit.
        direction: "spent" or "received".
        currency_code: ISO 4217 currency code (e.g., "USD", "JPY").
        category_name: Optional category name (find-or-create).
        note: Optional note (max 200 chars).
        payment_method: Optional payment method string.
        tags: Optional list of tag strings (max 10).
        user_timezone: User's timezone string for computing local date.

    Returns:
        The created Transaction instance.

    Raises:
        TransactionValidationError: If input validation fails.
        OperationalError: If all DB retry attempts fail.
    """
    _validate_transaction_input(
        amount_smallest_unit=amount_smallest_unit,
        direction=direction,
        currency_code=currency_code,
        note=note,
        tags=tags,
    )

    # Assign current UTC datetime
    now_utc = datetime.now(timezone.utc)

    # Compute local date from user timezone
    try:
        from zoneinfo import ZoneInfo

        user_tz = ZoneInfo(user_timezone)
        local_now = now_utc.astimezone(user_tz)
        transaction_date_local = local_now.date()
    except (KeyError, ImportError):
        # Fallback to UTC date if timezone is invalid
        transaction_date_local = now_utc.date()

    # Handle category
    category_id = None
    if category_name:
        category = _find_or_create_category(db, user_id, category_name)
        db.flush()  # Ensure category gets an ID
        category_id = category.id

    # Serialize tags
    tags_json = json.dumps(tags) if tags else None

    # Create transaction
    transaction = Transaction(
        user_id=user_id,
        amount_smallest_unit=amount_smallest_unit,
        direction=TransactionDirection(direction),
        currency_code=currency_code.upper(),
        category_id=category_id,
        note=note,
        payment_method=payment_method,
        tags_json=tags_json,
        transaction_datetime_utc=now_utc,
        transaction_date_local=transaction_date_local,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


def get_transactions(
    db: Session,
    user_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[int] = None,
    limit: int = 50,
) -> list[Transaction]:
    """Query transactions for a user with optional filters.

    Args:
        db: Database session.
        user_id: The user's ID.
        date_from: Optional start date filter (inclusive, uses transaction_date_local).
        date_to: Optional end date filter (inclusive, uses transaction_date_local).
        category_id: Optional category filter.
        limit: Maximum number of results (default 50).

    Returns:
        List of Transaction instances ordered by transaction_datetime_utc descending.
    """
    query = db.query(Transaction).filter(Transaction.user_id == user_id)

    if date_from is not None:
        query = query.filter(Transaction.transaction_date_local >= date_from)

    if date_to is not None:
        query = query.filter(Transaction.transaction_date_local <= date_to)

    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    query = query.order_by(Transaction.transaction_datetime_utc.desc())
    query = query.limit(limit)

    return query.all()


def get_frequent_categories(
    db: Session,
    user_id: int,
    days: int = 30,
    limit: int = 5,
) -> list[str]:
    """Get the top N most frequently used categories in the last N days.

    Queries categories for the user ordered by usage_count descending,
    filtered to categories that were used within the specified number of days.

    Args:
        db: Database session.
        user_id: The user's ID.
        days: Number of days to look back (default 30).
        limit: Maximum number of categories to return (default 5).

    Returns:
        List of category names, ordered by usage count descending.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    categories = (
        db.query(Category)
        .filter(
            Category.user_id == user_id,
            Category.last_used_at_utc >= cutoff_date,
        )
        .order_by(Category.usage_count.desc())
        .limit(limit)
        .all()
    )

    return [cat.name for cat in categories]


# Minimum categorized transactions required before suggestions are shown
MIN_CATEGORIZED_TRANSACTIONS = 5


def _get_categorized_transaction_count(db: Session, user_id: int) -> int:
    """Count the number of categorized transactions for a user.

    Args:
        db: Database session.
        user_id: The user's ID.

    Returns:
        Count of transactions that have a category assigned.
    """
    return (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.category_id.isnot(None),
        )
        .count()
    )


def _get_override_category(
    db: Session, user_id: int, note: Optional[str], amount: Optional[int]
) -> Optional[str]:
    """Check if user has an override for the given note or amount pattern.

    Looks for the most recent override matching:
    - Exact note match (if note provided)
    - Amount within 10% proximity (if amount provided)

    Note-based overrides take priority over amount-based overrides.

    Args:
        db: Database session.
        user_id: The user's ID.
        note: Transaction note to match.
        amount: Transaction amount in smallest currency unit to match.

    Returns:
        Category name if an override exists, None otherwise.
    """
    # Check note-based override first (higher priority)
    if note:
        override = (
            db.query(CategoryOverride)
            .join(Category, CategoryOverride.category_id == Category.id)
            .filter(
                CategoryOverride.user_id == user_id,
                CategoryOverride.note == note,
            )
            .order_by(CategoryOverride.created_at_utc.desc())
            .first()
        )
        if override:
            category = db.query(Category).filter(Category.id == override.category_id).first()
            if category:
                return category.name

    # Check amount-based override (10% proximity)
    if amount is not None and amount > 0:
        lower_bound = int(amount * 0.9)
        upper_bound = int(amount * 1.1)
        override = (
            db.query(CategoryOverride)
            .join(Category, CategoryOverride.category_id == Category.id)
            .filter(
                CategoryOverride.user_id == user_id,
                CategoryOverride.amount_smallest_unit.isnot(None),
                CategoryOverride.amount_smallest_unit >= lower_bound,
                CategoryOverride.amount_smallest_unit <= upper_bound,
            )
            .order_by(CategoryOverride.created_at_utc.desc())
            .first()
        )
        if override:
            category = db.query(Category).filter(Category.id == override.category_id).first()
            if category:
                return category.name

    return None


def _get_category_by_note_match(
    db: Session, user_id: int, note: str
) -> Optional[str]:
    """Find the most frequently used category for transactions with an exact note match.

    Args:
        db: Database session.
        user_id: The user's ID.
        note: The note to match exactly.

    Returns:
        The most frequently used category name for this note, or None.
    """
    # Find transactions with exact note match that have a category
    result = (
        db.query(Category.name, func.count(Transaction.id).label("match_count"))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.note == note,
            Transaction.category_id.isnot(None),
        )
        .group_by(Category.name)
        .order_by(func.count(Transaction.id).desc())
        .first()
    )

    if result:
        return result[0]
    return None


def _get_category_by_amount_proximity(
    db: Session, user_id: int, amount: int
) -> Optional[str]:
    """Find the most frequently used category for transactions within 10% of the given amount.

    Args:
        db: Database session.
        user_id: The user's ID.
        amount: The amount in smallest currency unit to match.

    Returns:
        The most frequently used category name for amounts within 10%, or None.
    """
    if amount <= 0:
        return None

    lower_bound = int(amount * 0.9)
    upper_bound = int(amount * 1.1)

    result = (
        db.query(Category.name, func.count(Transaction.id).label("match_count"))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.amount_smallest_unit >= lower_bound,
            Transaction.amount_smallest_unit <= upper_bound,
            Transaction.category_id.isnot(None),
        )
        .group_by(Category.name)
        .order_by(func.count(Transaction.id).desc())
        .first()
    )

    if result:
        return result[0]
    return None


def suggest_category(
    db: Session,
    user_id: int,
    note: Optional[str] = None,
    amount: Optional[int] = None,
) -> Optional[str]:
    """Suggest a category for a new transaction based on historical patterns.

    Priority order:
    1. User override — if the user has previously overridden a suggestion for
       the same note or amount pattern, return that category.
    2. Exact note match — if the note exactly matches a previously categorized
       transaction's note, return the most frequently used category for that note.
    3. Amount proximity — if the amount is within 10% of a previously categorized
       transaction's amount, return the most frequently used category for that amount range.

    Returns None if:
    - The user has fewer than 5 categorized transactions in history.
    - No matching pattern is found.
    - Both note and amount are None.

    Args:
        db: Database session.
        user_id: The user's ID.
        note: Optional transaction note to match.
        amount: Optional transaction amount in smallest currency unit.

    Returns:
        Suggested category name, or None if no suggestion available.
    """
    # Requirement 4.3: Don't suggest if fewer than 5 categorized transactions
    if _get_categorized_transaction_count(db, user_id) < MIN_CATEGORIZED_TRANSACTIONS:
        return None

    # If neither note nor amount provided, can't suggest
    if note is None and amount is None:
        return None

    # Priority 1: Check user overrides
    override_category = _get_override_category(db, user_id, note, amount)
    if override_category:
        return override_category

    # Priority 2: Exact note match
    if note:
        note_category = _get_category_by_note_match(db, user_id, note)
        if note_category:
            return note_category

    # Priority 3: 10% amount proximity
    if amount is not None:
        amount_category = _get_category_by_amount_proximity(db, user_id, amount)
        if amount_category:
            return amount_category

    return None


def record_category_override(
    db: Session,
    user_id: int,
    category_name: str,
    note: Optional[str] = None,
    amount: Optional[int] = None,
) -> CategoryOverride:
    """Record a user's category override for future suggestion prioritization.

    When a user overrides a suggested category, store the pattern (note and/or amount)
    and the chosen category so future suggestions prioritize the user's preference.

    Args:
        db: Database session.
        user_id: The user's ID.
        category_name: The category name the user chose.
        note: The transaction note (if available).
        amount: The transaction amount in smallest currency unit (if available).

    Returns:
        The created CategoryOverride record.
    """
    # Find or create the category
    category = _find_or_create_category(db, user_id, category_name)
    db.flush()

    override = CategoryOverride(
        user_id=user_id,
        note=note,
        amount_smallest_unit=amount,
        category_id=category.id,
        created_at_utc=datetime.now(timezone.utc),
    )
    db.add(override)
    db.commit()
    db.refresh(override)

    return override
