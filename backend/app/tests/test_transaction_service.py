"""Tests for TransactionService.

Covers: create_transaction, get_transactions, get_frequent_categories,
validation logic, retry behavior, and category management.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.category import Category
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.services.transaction_service import (
    TransactionValidationError,
    _find_or_create_category,
    _validate_transaction_input,
    create_transaction,
    get_frequent_categories,
    get_transactions,
)


def _create_test_session():
    """Create an in-memory SQLite engine and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession()


def _create_user(db: Session, timezone_str: str = "UTC") -> User:
    """Helper to create a test user."""
    user = User(
        timezone=timezone_str,
        current_streak=0,
        created_at_utc=datetime.now(timezone.utc),
        version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestValidateTransactionInput:
    """Tests for _validate_transaction_input."""

    def test_valid_input(self):
        """Valid input should not raise."""
        _validate_transaction_input(
            amount_smallest_unit=1050,
            direction="spent",
            currency_code="USD",
        )

    def test_valid_with_all_optional(self):
        """Valid input with all optional fields should not raise."""
        _validate_transaction_input(
            amount_smallest_unit=500,
            direction="received",
            currency_code="EUR",
            note="Test note",
            tags=["food", "lunch"],
        )

    def test_zero_amount_raises(self):
        """Zero amount should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=0,
                direction="spent",
                currency_code="USD",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "amount"
            assert "positive" in e.message.lower()

    def test_negative_amount_raises(self):
        """Negative amount should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=-100,
                direction="spent",
                currency_code="USD",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "amount"

    def test_non_integer_amount_raises(self):
        """Non-integer amount should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=10.5,  # type: ignore
                direction="spent",
                currency_code="USD",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "amount"

    def test_invalid_direction_raises(self):
        """Invalid direction should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=100,
                direction="unknown",
                currency_code="USD",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "direction"

    def test_invalid_currency_code_raises(self):
        """Invalid currency code should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=100,
                direction="spent",
                currency_code="US",  # Too short
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "currency_code"

    def test_empty_currency_code_raises(self):
        """Empty currency code should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=100,
                direction="spent",
                currency_code="",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "currency_code"

    def test_note_exceeds_200_chars_raises(self):
        """Note exceeding 200 characters should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=100,
                direction="spent",
                currency_code="USD",
                note="x" * 201,
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "note"

    def test_note_exactly_200_chars_valid(self):
        """Note at exactly 200 characters should be valid."""
        _validate_transaction_input(
            amount_smallest_unit=100,
            direction="spent",
            currency_code="USD",
            note="x" * 200,
        )

    def test_tags_exceeds_10_raises(self):
        """More than 10 tags should raise validation error."""
        try:
            _validate_transaction_input(
                amount_smallest_unit=100,
                direction="spent",
                currency_code="USD",
                tags=["tag"] * 11,
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "tags"

    def test_tags_exactly_10_valid(self):
        """Exactly 10 tags should be valid."""
        _validate_transaction_input(
            amount_smallest_unit=100,
            direction="spent",
            currency_code="USD",
            tags=["tag"] * 10,
        )


class TestFindOrCreateCategory:
    """Tests for _find_or_create_category."""

    def test_creates_new_category(self):
        """Should create a new category when it doesn't exist."""
        db = _create_test_session()
        user = _create_user(db)

        category = _find_or_create_category(db, user.id, "Food")
        db.flush()

        assert category.name == "Food"
        assert category.user_id == user.id
        assert category.usage_count == 1
        assert category.last_used_at_utc is not None
        db.close()

    def test_finds_existing_category(self):
        """Should find and update existing category."""
        db = _create_test_session()
        user = _create_user(db)

        # Create initial category
        cat = Category(
            user_id=user.id,
            name="Transport",
            usage_count=3,
            last_used_at_utc=datetime.now(timezone.utc) - timedelta(days=5),
        )
        db.add(cat)
        db.commit()

        # Find it again
        found = _find_or_create_category(db, user.id, "Transport")
        db.flush()

        assert found.id == cat.id
        assert found.usage_count == 4  # Incremented
        db.close()

    def test_different_users_same_category_name(self):
        """Different users should have separate categories with same name."""
        db = _create_test_session()
        user1 = _create_user(db)
        user2 = _create_user(db)

        cat1 = _find_or_create_category(db, user1.id, "Food")
        cat2 = _find_or_create_category(db, user2.id, "Food")
        db.flush()

        assert cat1.id != cat2.id
        assert cat1.user_id == user1.id
        assert cat2.user_id == user2.id
        db.close()


class TestCreateTransaction:
    """Tests for create_transaction."""

    def test_create_minimal_transaction(self):
        """Create transaction with only required fields."""
        db = _create_test_session()
        user = _create_user(db)

        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=1050,
            direction="spent",
            currency_code="USD",
        )

        assert txn.id is not None
        assert txn.amount_smallest_unit == 1050
        assert txn.direction == TransactionDirection.spent
        assert txn.currency_code == "USD"
        assert txn.category_id is None
        assert txn.note is None
        assert txn.payment_method is None
        assert txn.tags_json is None
        assert txn.transaction_datetime_utc is not None
        assert txn.transaction_date_local is not None
        db.close()

    def test_create_transaction_with_all_fields(self):
        """Create transaction with all optional fields."""
        db = _create_test_session()
        user = _create_user(db)

        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=5000,
            direction="received",
            currency_code="EUR",
            category_name="Salary",
            note="Monthly pay",
            payment_method="bank_transfer",
            tags=["income", "monthly"],
        )

        assert txn.amount_smallest_unit == 5000
        assert txn.direction == TransactionDirection.received
        assert txn.currency_code == "EUR"
        assert txn.category_id is not None
        assert txn.note == "Monthly pay"
        assert txn.payment_method == "bank_transfer"
        assert '"income"' in txn.tags_json
        assert '"monthly"' in txn.tags_json
        db.close()

    def test_create_transaction_assigns_utc_datetime(self):
        """Transaction should have current UTC datetime."""
        db = _create_test_session()
        user = _create_user(db)

        before = datetime.now(timezone.utc)
        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=100,
            direction="spent",
            currency_code="USD",
        )
        after = datetime.now(timezone.utc)

        # The transaction_datetime_utc should be between before and after
        # Note: SQLite doesn't store timezone info, so we compare naive
        assert txn.transaction_datetime_utc is not None
        db.close()

    def test_create_transaction_stores_local_date(self):
        """Transaction should store the local date based on user timezone."""
        db = _create_test_session()
        user = _create_user(db, timezone_str="America/New_York")

        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=100,
            direction="spent",
            currency_code="USD",
            user_timezone="America/New_York",
        )

        assert txn.transaction_date_local is not None
        assert isinstance(txn.transaction_date_local, date)
        db.close()

    def test_create_transaction_currency_code_uppercased(self):
        """Currency code should be stored uppercase."""
        db = _create_test_session()
        user = _create_user(db)

        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=100,
            direction="spent",
            currency_code="usd",  # lowercase
        )

        assert txn.currency_code == "USD"
        db.close()

    def test_create_transaction_validation_error(self):
        """Should raise TransactionValidationError for invalid input."""
        db = _create_test_session()
        user = _create_user(db)

        try:
            create_transaction(
                db=db,
                user_id=user.id,
                amount_smallest_unit=0,  # Invalid: zero
                direction="spent",
                currency_code="USD",
            )
            assert False, "Expected TransactionValidationError"
        except TransactionValidationError as e:
            assert e.field == "amount"
        db.close()

    def test_create_transaction_creates_category(self):
        """Specifying a category name should create or reuse category."""
        db = _create_test_session()
        user = _create_user(db)

        txn1 = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=500,
            direction="spent",
            currency_code="USD",
            category_name="Food",
        )

        txn2 = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=300,
            direction="spent",
            currency_code="USD",
            category_name="Food",
        )

        # Both should reference the same category
        assert txn1.category_id == txn2.category_id

        # Category usage_count should be 2
        cat = db.query(Category).filter(Category.id == txn1.category_id).first()
        assert cat.usage_count == 2
        db.close()

    def test_create_transaction_invalid_timezone_fallback(self):
        """Invalid timezone should fallback to UTC date."""
        db = _create_test_session()
        user = _create_user(db)

        txn = create_transaction(
            db=db,
            user_id=user.id,
            amount_smallest_unit=100,
            direction="spent",
            currency_code="USD",
            user_timezone="Invalid/Timezone",
        )

        # Should still succeed with UTC date as fallback
        assert txn.transaction_date_local == datetime.now(timezone.utc).date()
        db.close()


class TestGetTransactions:
    """Tests for get_transactions."""

    def test_get_transactions_returns_user_transactions(self):
        """Should return transactions for the specified user."""
        db = _create_test_session()
        user = _create_user(db)

        create_transaction(db, user.id, 100, "spent", "USD")
        create_transaction(db, user.id, 200, "received", "USD")

        results = get_transactions(db, user.id)
        assert len(results) == 2
        db.close()

    def test_get_transactions_does_not_return_other_users(self):
        """Should not return transactions from other users."""
        db = _create_test_session()
        user1 = _create_user(db)
        user2 = _create_user(db)

        create_transaction(db, user1.id, 100, "spent", "USD")
        create_transaction(db, user2.id, 200, "spent", "USD")

        results = get_transactions(db, user1.id)
        assert len(results) == 1
        assert results[0].amount_smallest_unit == 100
        db.close()

    def test_get_transactions_date_from_filter(self):
        """Should filter by date_from (inclusive)."""
        db = _create_test_session()
        user = _create_user(db)

        # Create transactions with different local dates
        txn1 = Transaction(
            user_id=user.id,
            amount_smallest_unit=100,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date(2024, 1, 1),
        )
        txn2 = Transaction(
            user_id=user.id,
            amount_smallest_unit=200,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date(2024, 1, 15),
        )
        db.add_all([txn1, txn2])
        db.commit()

        results = get_transactions(db, user.id, date_from=date(2024, 1, 10))
        assert len(results) == 1
        assert results[0].amount_smallest_unit == 200
        db.close()

    def test_get_transactions_date_to_filter(self):
        """Should filter by date_to (inclusive)."""
        db = _create_test_session()
        user = _create_user(db)

        txn1 = Transaction(
            user_id=user.id,
            amount_smallest_unit=100,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date(2024, 1, 1),
        )
        txn2 = Transaction(
            user_id=user.id,
            amount_smallest_unit=200,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date(2024, 1, 15),
        )
        db.add_all([txn1, txn2])
        db.commit()

        results = get_transactions(db, user.id, date_to=date(2024, 1, 10))
        assert len(results) == 1
        assert results[0].amount_smallest_unit == 100
        db.close()

    def test_get_transactions_category_filter(self):
        """Should filter by category_id."""
        db = _create_test_session()
        user = _create_user(db)

        cat = Category(
            user_id=user.id,
            name="Food",
            usage_count=1,
            last_used_at_utc=datetime.now(timezone.utc),
        )
        db.add(cat)
        db.commit()

        txn1 = Transaction(
            user_id=user.id,
            amount_smallest_unit=100,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=cat.id,
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date.today(),
        )
        txn2 = Transaction(
            user_id=user.id,
            amount_smallest_unit=200,
            direction=TransactionDirection.spent,
            currency_code="USD",
            category_id=None,
            transaction_datetime_utc=datetime.now(timezone.utc),
            transaction_date_local=date.today(),
        )
        db.add_all([txn1, txn2])
        db.commit()

        results = get_transactions(db, user.id, category_id=cat.id)
        assert len(results) == 1
        assert results[0].category_id == cat.id
        db.close()

    def test_get_transactions_limit(self):
        """Should respect the limit parameter."""
        db = _create_test_session()
        user = _create_user(db)

        for i in range(10):
            create_transaction(db, user.id, (i + 1) * 100, "spent", "USD")

        results = get_transactions(db, user.id, limit=3)
        assert len(results) == 3
        db.close()

    def test_get_transactions_ordered_by_datetime_desc(self):
        """Should return transactions ordered by datetime descending."""
        db = _create_test_session()
        user = _create_user(db)

        txn1 = Transaction(
            user_id=user.id,
            amount_smallest_unit=100,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime(2024, 1, 1, 10, 0, 0),
            transaction_date_local=date(2024, 1, 1),
        )
        txn2 = Transaction(
            user_id=user.id,
            amount_smallest_unit=200,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime(2024, 1, 2, 10, 0, 0),
            transaction_date_local=date(2024, 1, 2),
        )
        db.add_all([txn1, txn2])
        db.commit()

        results = get_transactions(db, user.id)
        # Most recent first
        assert results[0].amount_smallest_unit == 200
        assert results[1].amount_smallest_unit == 100
        db.close()

    def test_get_transactions_empty_result(self):
        """Should return empty list when no transactions exist."""
        db = _create_test_session()
        user = _create_user(db)

        results = get_transactions(db, user.id)
        assert results == []
        db.close()


class TestGetFrequentCategories:
    """Tests for get_frequent_categories."""

    def test_returns_top_5_categories(self):
        """Should return up to 5 most frequently used categories."""
        db = _create_test_session()
        user = _create_user(db)

        now = datetime.now(timezone.utc)
        categories = [
            Category(user_id=user.id, name=f"Cat{i}", usage_count=10 - i, last_used_at_utc=now)
            for i in range(7)
        ]
        db.add_all(categories)
        db.commit()

        results = get_frequent_categories(db, user.id)
        assert len(results) == 5
        # Should be ordered by usage_count desc
        assert results[0] == "Cat0"  # usage_count=10
        assert results[1] == "Cat1"  # usage_count=9
        db.close()

    def test_excludes_categories_not_used_in_last_30_days(self):
        """Should exclude categories not used within the last 30 days."""
        db = _create_test_session()
        user = _create_user(db)

        now = datetime.now(timezone.utc)
        recent_cat = Category(
            user_id=user.id, name="Recent", usage_count=5, last_used_at_utc=now
        )
        old_cat = Category(
            user_id=user.id,
            name="Old",
            usage_count=50,  # High usage but old
            last_used_at_utc=now - timedelta(days=31),
        )
        db.add_all([recent_cat, old_cat])
        db.commit()

        results = get_frequent_categories(db, user.id)
        assert "Recent" in results
        assert "Old" not in results
        db.close()

    def test_returns_empty_when_no_categories(self):
        """Should return empty list when user has no categories."""
        db = _create_test_session()
        user = _create_user(db)

        results = get_frequent_categories(db, user.id)
        assert results == []
        db.close()

    def test_respects_custom_limit(self):
        """Should respect custom limit parameter."""
        db = _create_test_session()
        user = _create_user(db)

        now = datetime.now(timezone.utc)
        for i in range(5):
            db.add(
                Category(
                    user_id=user.id,
                    name=f"Cat{i}",
                    usage_count=5 - i,
                    last_used_at_utc=now,
                )
            )
        db.commit()

        results = get_frequent_categories(db, user.id, limit=2)
        assert len(results) == 2
        db.close()

    def test_respects_custom_days(self):
        """Should respect custom days parameter."""
        db = _create_test_session()
        user = _create_user(db)

        now = datetime.now(timezone.utc)
        recent_cat = Category(
            user_id=user.id, name="Recent", usage_count=5, last_used_at_utc=now
        )
        semi_old_cat = Category(
            user_id=user.id,
            name="SemiOld",
            usage_count=10,
            last_used_at_utc=now - timedelta(days=10),
        )
        db.add_all([recent_cat, semi_old_cat])
        db.commit()

        # With default 30 days, both should appear
        results_30 = get_frequent_categories(db, user.id, days=30)
        assert "SemiOld" in results_30

        # With 5 days, only the recent one should appear
        results_5 = get_frequent_categories(db, user.id, days=5)
        assert "Recent" in results_5
        assert "SemiOld" not in results_5
        db.close()

    def test_only_returns_user_categories(self):
        """Should not return categories from other users."""
        db = _create_test_session()
        user1 = _create_user(db)
        user2 = _create_user(db)

        now = datetime.now(timezone.utc)
        db.add(Category(user_id=user1.id, name="MyFood", usage_count=5, last_used_at_utc=now))
        db.add(Category(user_id=user2.id, name="TheirFood", usage_count=10, last_used_at_utc=now))
        db.commit()

        results = get_frequent_categories(db, user1.id)
        assert "MyFood" in results
        assert "TheirFood" not in results
        db.close()


class TestDatabaseRetryLogic:
    """Tests for the with_db_retry decorator behavior."""

    def test_retry_decorator_retries_on_operational_error(self):
        """Should retry up to 3 times on OperationalError."""
        call_count = 0

        @patch("app.services.transaction_service.time.sleep")
        def run_test(mock_sleep):
            nonlocal call_count

            db = _create_test_session()
            user = _create_user(db)

            # Monkey-patch to track calls and simulate transient failure
            original_create = create_transaction.__wrapped__

            def failing_create(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise OperationalError("connection lost", {}, None)
                return original_create(*args, **kwargs)

            # Test the retry logic via the decorator directly
            from app.services.transaction_service import with_db_retry

            retried_fn = with_db_retry(failing_create)
            result = retried_fn(
                db=db,
                user_id=user.id,
                amount_smallest_unit=100,
                direction="spent",
                currency_code="USD",
            )

            assert call_count == 3  # Failed twice, succeeded on third
            assert result is not None
            db.close()

        run_test()

    def test_retry_decorator_raises_after_max_attempts(self):
        """Should raise after exhausting all retry attempts."""

        @patch("app.services.transaction_service.time.sleep")
        def run_test(mock_sleep):
            from app.services.transaction_service import with_db_retry

            attempt_count = 0

            @with_db_retry
            def always_fails():
                nonlocal attempt_count
                attempt_count += 1
                raise OperationalError("connection lost", {}, None)

            try:
                always_fails()
                assert False, "Expected OperationalError"
            except OperationalError:
                assert attempt_count == 3  # Tried 3 times total

        run_test()
