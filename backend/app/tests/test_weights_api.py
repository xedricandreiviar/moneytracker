"""Tests for category weights API endpoints.

Covers: GET /api/weights, PUT /api/weights/{category_name},
POST /api/weights/reset, and error handling (400, 404, 422).

Requirements: 16.1, 16.4, 16.5, 16.6
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.category_weight import CategoryWeight
from app.models.user import CommuteMethod, EmploymentStatus, User


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
def test_user_profile_completed(test_db):
    """Create a test user with profile_completed=True and a lifestyle profile."""
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
def test_user_no_profile(test_db):
    """Create a test user with profile_completed=False."""
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
def test_user_with_weights(test_db, test_user_profile_completed):
    """Create a test user with pre-existing category weights."""
    weights = [
        CategoryWeight(
            user_id=1,
            category_name="Savings",
            weight_percentage=Decimal("30.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=1,
            category_name="Wants",
            weight_percentage=Decimal("25.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=1,
            category_name="Transportation",
            weight_percentage=Decimal("15.00"),
            is_manual_override=False,
        ),
        CategoryWeight(
            user_id=1,
            category_name="Food",
            weight_percentage=Decimal("30.00"),
            is_manual_override=False,
        ),
    ]
    for w in weights:
        test_db.add(w)
    test_db.commit()
    return test_user_profile_completed


class TestGetWeights:
    """Tests for GET /api/weights."""

    def test_get_weights_returns_all_entries(self, client, test_user_with_weights):
        """Should return all category weight entries for the user."""
        response = client.get("/api/weights")

        assert response.status_code == 200
        data = response.json()
        assert "weights" in data
        assert "total_percentage" in data
        assert len(data["weights"]) == 4

    def test_get_weights_total_is_100(self, client, test_user_with_weights):
        """Should have total_percentage equal to 100.00."""
        response = client.get("/api/weights")

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["total_percentage"])) == Decimal("100.00")

    def test_get_weights_returns_correct_fields(self, client, test_user_with_weights):
        """Each weight entry should have category_name, weight_percentage, is_manual_override."""
        response = client.get("/api/weights")

        assert response.status_code == 200
        data = response.json()
        for weight in data["weights"]:
            assert "category_name" in weight
            assert "weight_percentage" in weight
            assert "is_manual_override" in weight

    def test_get_weights_empty_when_no_weights(self, client, test_user_profile_completed):
        """Should return empty list when no weights exist."""
        response = client.get("/api/weights")

        assert response.status_code == 200
        data = response.json()
        assert data["weights"] == []
        assert Decimal(str(data["total_percentage"])) == Decimal("0")

    def test_get_weights_returns_400_if_profile_not_completed(self, client, test_user_no_profile):
        """Should return 400 if user's profile has not been completed."""
        response = client.get("/api/weights")

        assert response.status_code == 400
        data = response.json()
        assert "Profile not completed" in data["detail"]


class TestOverrideWeight:
    """Tests for PUT /api/weights/{category_name}."""

    def test_override_weight_success(self, client, test_user_with_weights):
        """Should successfully override a weight and return updated list."""
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 40},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["weights"]) == 4
        # Total should still be 100
        assert Decimal(str(data["total_percentage"])) == Decimal("100.00")

        # Find the overridden category
        savings = next(w for w in data["weights"] if w["category_name"] == "Savings")
        assert Decimal(str(savings["weight_percentage"])) == Decimal("40.00")
        assert savings["is_manual_override"] is True

    def test_override_weight_redistributes_others(self, client, test_user_with_weights):
        """Should proportionally redistribute remaining categories."""
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 50},
        )

        assert response.status_code == 200
        data = response.json()
        # Others should share the remaining 50%
        others = [w for w in data["weights"] if w["category_name"] != "Savings"]
        others_total = sum(Decimal(str(w["weight_percentage"])) for w in others)
        assert others_total == Decimal("50.00")

    def test_override_weight_returns_400_if_profile_not_completed(self, client, test_user_no_profile):
        """Should return 400 if profile not completed."""
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 40},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Profile not completed" in data["detail"]

    def test_override_weight_returns_404_if_category_not_found(self, client, test_user_with_weights):
        """Should return 404 if category does not exist for user."""
        response = client.put(
            "/api/weights/NonExistent",
            json={"category_name": "NonExistent", "new_percentage": 20},
        )

        assert response.status_code == 404

    def test_override_weight_returns_422_no_redistribution(self, client, test_db, test_user_profile_completed):
        """Should return 422 when override would leave no categories for redistribution."""
        # Create weights where all others are already manually overridden
        weights = [
            CategoryWeight(
                user_id=1,
                category_name="Savings",
                weight_percentage=Decimal("30.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Wants",
                weight_percentage=Decimal("30.00"),
                is_manual_override=True,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Transportation",
                weight_percentage=Decimal("20.00"),
                is_manual_override=True,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Food",
                weight_percentage=Decimal("20.00"),
                is_manual_override=True,
            ),
        ]
        for w in weights:
            test_db.add(w)
        test_db.commit()

        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 40},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_override_weight_validates_percentage_range(self, client, test_user_with_weights):
        """Should return 422 if new_percentage is 0 or >= 100."""
        # Test 0
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 0},
        )
        assert response.status_code == 422

        # Test 100
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": 100},
        )
        assert response.status_code == 422

        # Test negative
        response = client.put(
            "/api/weights/Savings",
            json={"category_name": "Savings", "new_percentage": -5},
        )
        assert response.status_code == 422


class TestResetWeights:
    """Tests for POST /api/weights/reset."""

    def test_reset_weights_success(self, client, test_user_with_weights):
        """Should recompute weights from profile defaults."""
        response = client.post("/api/weights/reset")

        assert response.status_code == 200
        data = response.json()
        assert "weights" in data
        assert len(data["weights"]) == 4
        assert Decimal(str(data["total_percentage"])) == Decimal("100.00")

    def test_reset_weights_clears_manual_overrides(self, client, test_db, test_user_profile_completed):
        """Should clear all manual override flags after reset."""
        # Create weights with manual overrides
        weights = [
            CategoryWeight(
                user_id=1,
                category_name="Savings",
                weight_percentage=Decimal("50.00"),
                is_manual_override=True,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Wants",
                weight_percentage=Decimal("20.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Transportation",
                weight_percentage=Decimal("10.00"),
                is_manual_override=False,
            ),
            CategoryWeight(
                user_id=1,
                category_name="Food",
                weight_percentage=Decimal("20.00"),
                is_manual_override=False,
            ),
        ]
        for w in weights:
            test_db.add(w)
        test_db.commit()

        response = client.post("/api/weights/reset")

        assert response.status_code == 200
        data = response.json()
        # After reset, no weights should be manually overridden
        for weight in data["weights"]:
            assert weight["is_manual_override"] is False

    def test_reset_weights_returns_400_if_profile_not_completed(self, client, test_user_no_profile):
        """Should return 400 if profile not completed."""
        response = client.post("/api/weights/reset")

        assert response.status_code == 400
        data = response.json()
        assert "Profile not completed" in data["detail"]

    def test_reset_weights_uses_profile_values(self, client, test_user_with_weights):
        """Should derive weights from current profile (working, public_transit)."""
        response = client.post("/api/weights/reset")

        assert response.status_code == 200
        data = response.json()
        # Expected for working + public_transit:
        # Savings: 30, Wants: 25, Transportation: 15, Food: 30
        weights_map = {w["category_name"]: w["weight_percentage"] for w in data["weights"]}
        assert Decimal(str(weights_map["Savings"])) == Decimal("30.00")
        assert Decimal(str(weights_map["Wants"])) == Decimal("25.00")
        assert Decimal(str(weights_map["Transportation"])) == Decimal("15.00")
        assert Decimal(str(weights_map["Food"])) == Decimal("30.00")
