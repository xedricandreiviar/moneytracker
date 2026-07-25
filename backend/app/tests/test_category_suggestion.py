"""Tests for category suggestion logic in TransactionService.

Covers: suggest_category, record_category_override, and the priority system
(user override → exact note match → 10% amount proximity).
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.category import Category
from app.models.category_override import CategoryOverride
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User
from app.services.transaction_service import (
    record_category_override,
    suggest_category,
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


def _create_category(db: Session, user_id: int, name: str, usage_count: int = 1) -> Category:
    """Helper to create a category for a user."""
    cat = Category(
        user_id=user_id,
        name=name,
        usage_count=usage_count,
        last_used_at_utc=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _create_categorized_transaction(
    db: Session,
    user_id: int,
    category_id: int,
    amount: int = 1000,
    note: str | None = None,
) -> Transaction:
    """Helper to create a categorized transaction."""
    txn = Transaction(
        user_id=user_id,
        amount_smallest_unit=amount,
        direction=TransactionDirection.spent,
        currency_code="USD",
        category_id=category_id,
        note=note,
        transaction_datetime_utc=datetime.now(timezone.utc),
        transaction_date_local=date.today(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def _seed_categorized_transactions(db: Session, user_id: int, count: int = 5) -> Category:
    """Seed a user with N categorized transactions. Returns the category used."""
    cat = _create_category(db, user_id, "Food", usage_count=count)
    for i in range(count):
        _create_categorized_transaction(db, user_id, cat.id, amount=1000 + i * 100)
    return cat


class TestSuggestCategoryMinimumThreshold:
    """Tests for the minimum 5 categorized transactions requirement."""

    def test_returns_none_with_fewer_than_5_categorized_transactions(self):
        """Should return None when user has fewer than 5 categorized transactions."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")

        # Create only 4 categorized transactions
        for i in range(4):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000, note="coffee")

        result = suggest_category(db, user.id, note="coffee")
        assert result is None
        db.close()

    def test_returns_suggestion_with_exactly_5_categorized_transactions(self):
        """Should return a suggestion when user has exactly 5 categorized transactions."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")

        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000, note="coffee")

        result = suggest_category(db, user.id, note="coffee")
        assert result == "Food"
        db.close()

    def test_uncategorized_transactions_dont_count(self):
        """Transactions without a category should not count toward the 5 minimum."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")

        # 3 categorized
        for i in range(3):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000, note="coffee")

        # 5 uncategorized (category_id = None)
        for i in range(5):
            txn = Transaction(
                user_id=user.id,
                amount_smallest_unit=500,
                direction=TransactionDirection.spent,
                currency_code="USD",
                category_id=None,
                note="coffee",
                transaction_datetime_utc=datetime.now(timezone.utc),
                transaction_date_local=date.today(),
            )
            db.add(txn)
        db.commit()

        result = suggest_category(db, user.id, note="coffee")
        assert result is None
        db.close()


class TestSuggestCategoryNoteMatch:
    """Tests for exact note matching logic."""

    def test_exact_note_match_returns_most_frequent_category(self):
        """Should return the most frequently used category for exact note matches."""
        db = _create_test_session()
        user = _create_user(db)
        food_cat = _create_category(db, user.id, "Food", usage_count=3)
        drink_cat = _create_category(db, user.id, "Drinks", usage_count=2)

        # 3 transactions with note "coffee" in Food
        for i in range(3):
            _create_categorized_transaction(db, user.id, food_cat.id, note="coffee")
        # 2 transactions with note "coffee" in Drinks
        for i in range(2):
            _create_categorized_transaction(db, user.id, drink_cat.id, note="coffee")

        result = suggest_category(db, user.id, note="coffee")
        assert result == "Food"
        db.close()

    def test_note_match_is_case_sensitive(self):
        """Note matching should be case-sensitive (exact match)."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")

        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, note="Coffee")

        # Different case should not match
        result = suggest_category(db, user.id, note="coffee")
        assert result is None
        db.close()

    def test_no_match_returns_none(self):
        """Should return None when no note match is found."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _seed_categorized_transactions(db, user.id, count=5)

        result = suggest_category(db, user.id, note="nonexistent note")
        assert result is None
        db.close()


class TestSuggestCategoryAmountProximity:
    """Tests for 10% amount proximity matching."""

    def test_amount_within_10_percent_matches(self):
        """Should match amounts within 10% proximity."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Transport")

        # Create 5 transactions at 1000
        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000)

        # Query with amount 1050 (within 10% of 1000)
        result = suggest_category(db, user.id, amount=1050)
        assert result == "Transport"
        db.close()

    def test_amount_at_exactly_10_percent_boundary(self):
        """Amount at exactly 10% boundary should match."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Transport")

        # Create 5 transactions at 1000
        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000)

        # Query with amount 1100 (exactly 10% above 1000)
        # 1100 * 0.9 = 990, 1100 * 1.1 = 1210 — 1000 is within [990, 1210]
        result = suggest_category(db, user.id, amount=1100)
        assert result == "Transport"
        db.close()

    def test_amount_outside_10_percent_does_not_match(self):
        """Amounts outside 10% should not match."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Transport")

        # Create 5 transactions at 1000
        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, amount=1000)

        # Query with amount 2000 (not within 10% of 1000)
        # 2000 * 0.9 = 1800, 2000 * 1.1 = 2200 — 1000 not in [1800, 2200]
        result = suggest_category(db, user.id, amount=2000)
        assert result is None
        db.close()

    def test_amount_proximity_returns_most_frequent_category(self):
        """Should return the most frequent category among amount-proximate transactions."""
        db = _create_test_session()
        user = _create_user(db)
        food_cat = _create_category(db, user.id, "Food")
        transport_cat = _create_category(db, user.id, "Transport")

        # 3 transactions at 1000 in Food
        for i in range(3):
            _create_categorized_transaction(db, user.id, food_cat.id, amount=1000)
        # 2 transactions at 1050 in Transport
        for i in range(2):
            _create_categorized_transaction(db, user.id, transport_cat.id, amount=1050)

        # Query with 1020 — both 1000 and 1050 are within 10% of 1020
        result = suggest_category(db, user.id, amount=1020)
        assert result == "Food"  # More frequent
        db.close()


class TestSuggestCategoryPriority:
    """Tests for priority ordering: override → note → amount."""

    def test_note_match_takes_priority_over_amount(self):
        """Exact note match should take priority over amount proximity."""
        db = _create_test_session()
        user = _create_user(db)
        food_cat = _create_category(db, user.id, "Food")
        transport_cat = _create_category(db, user.id, "Transport")

        # Food: transactions with note "lunch" at amount 1500
        for i in range(3):
            _create_categorized_transaction(db, user.id, food_cat.id, amount=1500, note="lunch")
        # Transport: transactions at amount 1500 (no note or different note)
        for i in range(5):
            _create_categorized_transaction(db, user.id, transport_cat.id, amount=1500, note="uber")

        # Query with note="lunch" and amount=1500
        # Note match → Food (3 matches), Amount match → Transport (5 matches for amount but note takes priority)
        result = suggest_category(db, user.id, note="lunch", amount=1500)
        assert result == "Food"
        db.close()

    def test_override_takes_priority_over_note_match(self):
        """User override should take priority over exact note match."""
        db = _create_test_session()
        user = _create_user(db)
        food_cat = _create_category(db, user.id, "Food")
        drink_cat = _create_category(db, user.id, "Drinks")

        # 5 transactions with note "coffee" categorized as Food
        for i in range(5):
            _create_categorized_transaction(db, user.id, food_cat.id, note="coffee")

        # User overrides to Drinks for "coffee"
        record_category_override(db, user.id, "Drinks", note="coffee")

        result = suggest_category(db, user.id, note="coffee")
        assert result == "Drinks"
        db.close()

    def test_override_takes_priority_over_amount_match(self):
        """User override should take priority over amount proximity match."""
        db = _create_test_session()
        user = _create_user(db)
        food_cat = _create_category(db, user.id, "Food")
        transport_cat = _create_category(db, user.id, "Transport")

        # 5 transactions at amount 1000 in Food
        for i in range(5):
            _create_categorized_transaction(db, user.id, food_cat.id, amount=1000)

        # User override for amount ~1000 → Transport
        record_category_override(db, user.id, "Transport", amount=1000)

        result = suggest_category(db, user.id, amount=1000)
        assert result == "Transport"
        db.close()


class TestSuggestCategoryEdgeCases:
    """Tests for edge cases."""

    def test_returns_none_when_both_note_and_amount_are_none(self):
        """Should return None when neither note nor amount is provided."""
        db = _create_test_session()
        user = _create_user(db)
        _seed_categorized_transactions(db, user.id, count=5)

        result = suggest_category(db, user.id, note=None, amount=None)
        assert result is None
        db.close()

    def test_zero_amount_returns_none(self):
        """Should return None for zero amount (invalid)."""
        db = _create_test_session()
        user = _create_user(db)
        _seed_categorized_transactions(db, user.id, count=5)

        result = suggest_category(db, user.id, amount=0)
        assert result is None
        db.close()

    def test_negative_amount_returns_none(self):
        """Should return None for negative amount (invalid)."""
        db = _create_test_session()
        user = _create_user(db)
        _seed_categorized_transactions(db, user.id, count=5)

        result = suggest_category(db, user.id, amount=-100)
        assert result is None
        db.close()

    def test_empty_note_returns_none(self):
        """Empty string note should not match anything."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")
        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, note="coffee")

        result = suggest_category(db, user.id, note="")
        assert result is None
        db.close()


class TestRecordCategoryOverride:
    """Tests for record_category_override."""

    def test_creates_override_with_note(self):
        """Should create an override record with note pattern."""
        db = _create_test_session()
        user = _create_user(db)

        override = record_category_override(db, user.id, "Drinks", note="coffee")

        assert override.id is not None
        assert override.user_id == user.id
        assert override.note == "coffee"
        assert override.amount_smallest_unit is None
        assert override.category_id is not None
        db.close()

    def test_creates_override_with_amount(self):
        """Should create an override record with amount pattern."""
        db = _create_test_session()
        user = _create_user(db)

        override = record_category_override(db, user.id, "Transport", amount=1500)

        assert override.id is not None
        assert override.user_id == user.id
        assert override.note is None
        assert override.amount_smallest_unit == 1500
        db.close()

    def test_creates_override_with_both_note_and_amount(self):
        """Should create an override record with both note and amount."""
        db = _create_test_session()
        user = _create_user(db)

        override = record_category_override(
            db, user.id, "Food", note="lunch", amount=1200
        )

        assert override.note == "lunch"
        assert override.amount_smallest_unit == 1200
        db.close()

    def test_most_recent_override_wins(self):
        """When multiple overrides exist, the most recent should be used."""
        db = _create_test_session()
        user = _create_user(db)
        cat = _create_category(db, user.id, "Food")

        # Seed 5 categorized transactions
        for i in range(5):
            _create_categorized_transaction(db, user.id, cat.id, note="coffee")

        # First override to "Drinks"
        record_category_override(db, user.id, "Drinks", note="coffee")
        # Second override to "Snacks" (more recent)
        record_category_override(db, user.id, "Snacks", note="coffee")

        result = suggest_category(db, user.id, note="coffee")
        assert result == "Snacks"
        db.close()

    def test_override_creates_category_if_not_exists(self):
        """Recording an override should create the category if it doesn't exist."""
        db = _create_test_session()
        user = _create_user(db)

        override = record_category_override(db, user.id, "NewCategory", note="test")

        # Category should now exist
        cat = db.query(Category).filter(
            Category.user_id == user.id, Category.name == "NewCategory"
        ).first()
        assert cat is not None
        assert override.category_id == cat.id
        db.close()
