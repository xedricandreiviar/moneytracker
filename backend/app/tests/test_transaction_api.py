"""Tests for transaction API endpoints.

Covers: POST /api/transactions, GET /api/transactions,
GET /api/transactions/frequent-categories, and error handling.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.category import Category
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User


# --- Test database setup ---

# Use StaticPool + check_same_thread=False so SQLite works across threads
# (FastAPI TestClient runs the app in a separate thread)
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
    user = User(id=1, timezone="UTC", current_streak=0, version=1)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestCreateTransaction:
    """Tests for POST /api/transactions."""

    def test_create_transaction_success(self, client, test_user):
        """Should create a transaction with minimal required fields."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 1050,
                "direction": "spent",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["amount_smallest_unit"] == 1050
        assert data["direction"] == "spent"
        assert data["currency_code"] == "USD"
        assert data["id"] is not None
        assert data["user_id"] == 1
        assert data["category_name"] is None
        assert data["note"] is None
        assert data["tags"] is None
        assert data["transaction_datetime_utc"] is not None
        assert data["transaction_date_local"] is not None
        assert data["created_at_utc"] is not None

    def test_create_transaction_with_all_fields(self, client, test_user):
        """Should create a transaction with all optional fields."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 5000,
                "direction": "received",
                "currency_code": "EUR",
                "category_name": "Salary",
                "note": "Monthly pay",
                "payment_method": "bank_transfer",
                "tags": ["income", "monthly"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["amount_smallest_unit"] == 5000
        assert data["direction"] == "received"
        assert data["currency_code"] == "EUR"
        assert data["category_name"] == "Salary"
        assert data["note"] == "Monthly pay"
        assert data["payment_method"] == "bank_transfer"
        assert data["tags"] == ["income", "monthly"]

    def test_create_transaction_invalid_amount_zero(self, client, test_user):
        """Should return 422 for zero amount."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 0,
                "direction": "spent",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_transaction_invalid_amount_negative(self, client, test_user):
        """Should return 422 for negative amount."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": -100,
                "direction": "spent",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_transaction_invalid_direction(self, client, test_user):
        """Should return 422 for invalid direction."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100,
                "direction": "unknown",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422

    def test_create_transaction_invalid_currency_code_too_short(self, client, test_user):
        """Should return 422 for currency code less than 3 chars."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100,
                "direction": "spent",
                "currency_code": "US",
            },
        )

        assert response.status_code == 422

    def test_create_transaction_note_exceeds_200_chars(self, client, test_user):
        """Should return 422 for note exceeding 200 characters."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100,
                "direction": "spent",
                "currency_code": "USD",
                "note": "x" * 201,
            },
        )

        assert response.status_code == 422

    def test_create_transaction_tags_exceeds_10(self, client, test_user):
        """Should return 422 for more than 10 tags."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100,
                "direction": "spent",
                "currency_code": "USD",
                "tags": [f"tag{i}" for i in range(11)],
            },
        )

        assert response.status_code == 422

    def test_create_transaction_validation_error_has_field_detail(self, client, test_user):
        """Should return 422 with detail for validation failures."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": -5,
                "direction": "spent",
                "currency_code": "USD",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_transaction_currency_code_uppercased(self, client, test_user):
        """Currency code should be stored uppercased."""
        response = client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 100,
                "direction": "spent",
                "currency_code": "usd",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["currency_code"] == "USD"


class TestListTransactions:
    """Tests for GET /api/transactions."""

    def test_list_transactions_empty(self, client, test_user):
        """Should return empty list when no transactions exist."""
        response = client.get("/api/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["transactions"] == []
        assert data["count"] == 0

    def test_list_transactions_returns_created(self, client, test_user):
        """Should return transactions after creation."""
        client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 1050,
                "direction": "spent",
                "currency_code": "USD",
            },
        )
        client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 2000,
                "direction": "received",
                "currency_code": "USD",
            },
        )

        response = client.get("/api/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["transactions"]) == 2

    def test_list_transactions_with_limit(self, client, test_user):
        """Should respect limit parameter."""
        for i in range(5):
            client.post(
                "/api/transactions",
                json={
                    "amount_smallest_unit": (i + 1) * 100,
                    "direction": "spent",
                    "currency_code": "USD",
                },
            )

        response = client.get("/api/transactions?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_list_transactions_with_date_filters(self, client, test_user, test_db):
        """Should filter by date_from and date_to."""
        # Directly insert transactions with specific dates
        txn1 = Transaction(
            user_id=test_user.id,
            amount_smallest_unit=100,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime(2024, 1, 5, 10, 0, 0),
            transaction_date_local=date(2024, 1, 5),
        )
        txn2 = Transaction(
            user_id=test_user.id,
            amount_smallest_unit=200,
            direction=TransactionDirection.spent,
            currency_code="USD",
            transaction_datetime_utc=datetime(2024, 1, 20, 10, 0, 0),
            transaction_date_local=date(2024, 1, 20),
        )
        test_db.add_all([txn1, txn2])
        test_db.commit()

        # Filter from Jan 10 onwards
        response = client.get("/api/transactions?date_from=2024-01-10")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["transactions"][0]["amount_smallest_unit"] == 200

        # Filter up to Jan 10
        response = client.get("/api/transactions?date_to=2024-01-10")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["transactions"][0]["amount_smallest_unit"] == 100

    def test_list_transactions_with_category_filter(self, client, test_user, test_db):
        """Should filter by category_id."""
        # Create transactions with and without category via the API
        client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 500,
                "direction": "spent",
                "currency_code": "USD",
                "category_name": "Food",
            },
        )
        client.post(
            "/api/transactions",
            json={
                "amount_smallest_unit": 300,
                "direction": "spent",
                "currency_code": "USD",
            },
        )

        # Get the category_id from the first transaction
        all_response = client.get("/api/transactions")
        all_data = all_response.json()
        food_txn = next(
            t for t in all_data["transactions"] if t["category_name"] == "Food"
        )

        # Query the category from DB to get the ID
        cat = (
            test_db.query(Category)
            .filter(Category.user_id == test_user.id, Category.name == "Food")
            .first()
        )

        # Filter by category_id
        response = client.get(f"/api/transactions?category_id={cat.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["transactions"][0]["category_name"] == "Food"


class TestFrequentCategories:
    """Tests for GET /api/transactions/frequent-categories."""

    def test_frequent_categories_empty(self, client, test_user):
        """Should return empty list when no categories exist."""
        response = client.get("/api/transactions/frequent-categories")

        assert response.status_code == 200
        data = response.json()
        assert data["categories"] == []

    def test_frequent_categories_returns_used_categories(self, client, test_user, test_db):
        """Should return categories used within last 30 days."""
        now = datetime.now(timezone.utc)
        cat1 = Category(
            user_id=test_user.id, name="Food", usage_count=10, last_used_at_utc=now
        )
        cat2 = Category(
            user_id=test_user.id, name="Transport", usage_count=5, last_used_at_utc=now
        )
        test_db.add_all([cat1, cat2])
        test_db.commit()

        response = client.get("/api/transactions/frequent-categories")

        assert response.status_code == 200
        data = response.json()
        assert "Food" in data["categories"]
        assert "Transport" in data["categories"]
        # Should be ordered by usage_count desc
        assert data["categories"][0] == "Food"

    def test_frequent_categories_max_5(self, client, test_user, test_db):
        """Should return at most 5 categories."""
        now = datetime.now(timezone.utc)
        for i in range(7):
            test_db.add(
                Category(
                    user_id=test_user.id,
                    name=f"Cat{i}",
                    usage_count=10 - i,
                    last_used_at_utc=now,
                )
            )
        test_db.commit()

        response = client.get("/api/transactions/frequent-categories")

        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 5

    def test_frequent_categories_excludes_old(self, client, test_user, test_db):
        """Should exclude categories not used in last 30 days."""
        now = datetime.now(timezone.utc)
        recent = Category(
            user_id=test_user.id, name="Recent", usage_count=5, last_used_at_utc=now
        )
        old = Category(
            user_id=test_user.id,
            name="Old",
            usage_count=50,
            last_used_at_utc=now - timedelta(days=31),
        )
        test_db.add_all([recent, old])
        test_db.commit()

        response = client.get("/api/transactions/frequent-categories")

        assert response.status_code == 200
        data = response.json()
        assert "Recent" in data["categories"]
        assert "Old" not in data["categories"]


class TestSuggestCategory:
    """Tests for POST /api/transactions/suggest-category."""

    def test_suggest_category_no_history(self, client, test_user):
        """Should return null when user has fewer than 5 categorized transactions."""
        response = client.post(
            "/api/transactions/suggest-category",
            json={"note": "Coffee", "amount": 500},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_category"] is None

    def test_suggest_category_with_sufficient_history(self, client, test_user, test_db):
        """Should return a suggestion when user has 5+ categorized transactions with matching note."""
        # Create 5 categorized transactions with the same note
        cat = Category(
            user_id=test_user.id,
            name="Coffee",
            usage_count=5,
            last_used_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(cat)
        test_db.flush()

        for i in range(5):
            txn = Transaction(
                user_id=test_user.id,
                amount_smallest_unit=450 + i * 10,
                direction=TransactionDirection.spent,
                currency_code="USD",
                category_id=cat.id,
                note="Starbucks",
                transaction_datetime_utc=datetime.now(timezone.utc),
                transaction_date_local=date.today(),
            )
            test_db.add(txn)
        test_db.commit()

        response = client.post(
            "/api/transactions/suggest-category",
            json={"note": "Starbucks"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_category"] == "Coffee"

    def test_suggest_category_no_match(self, client, test_user, test_db):
        """Should return null when no matching patterns found."""
        # Create 5 categorized transactions with different note
        cat = Category(
            user_id=test_user.id,
            name="Food",
            usage_count=5,
            last_used_at_utc=datetime.now(timezone.utc),
        )
        test_db.add(cat)
        test_db.flush()

        for i in range(5):
            txn = Transaction(
                user_id=test_user.id,
                amount_smallest_unit=1000 + i * 100,
                direction=TransactionDirection.spent,
                currency_code="USD",
                category_id=cat.id,
                note="Lunch",
                transaction_datetime_utc=datetime.now(timezone.utc),
                transaction_date_local=date.today(),
            )
            test_db.add(txn)
        test_db.commit()

        response = client.post(
            "/api/transactions/suggest-category",
            json={"note": "Electricity Bill"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_category"] is None

    def test_suggest_category_empty_request(self, client, test_user):
        """Should return null when neither note nor amount provided."""
        response = client.post(
            "/api/transactions/suggest-category",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_category"] is None


class TestRecordOverride:
    """Tests for POST /api/transactions/record-override."""

    def test_record_override_success(self, client, test_user):
        """Should record an override and return success."""
        response = client.post(
            "/api/transactions/record-override",
            json={
                "category_name": "Transport",
                "note": "Uber ride",
                "amount": 2500,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["category_name"] == "Transport"

    def test_record_override_note_only(self, client, test_user):
        """Should record override with just a note pattern."""
        response = client.post(
            "/api/transactions/record-override",
            json={
                "category_name": "Food",
                "note": "Pizza",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_record_override_missing_category_name(self, client, test_user):
        """Should return 422 when category_name is missing."""
        response = client.post(
            "/api/transactions/record-override",
            json={"note": "Test"},
        )

        assert response.status_code == 422
