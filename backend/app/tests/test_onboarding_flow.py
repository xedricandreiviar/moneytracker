"""Integration test: End-to-end onboarding flow.

Verifies the complete flow:
1. New user starts with profile_completed=False
2. Backend middleware blocks protected routes
3. PUT /api/profile sets profile_completed=True
4. Weight recomputation triggers on first profile submission
5. Derived weights reflect the Weight_Rules_Table for the given profile
6. After profile completion, dashboard endpoints become accessible

Requirements: 15.1, 15.6, 16.3
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.category_weight import CategoryWeight
from app.models.user import User
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
def new_user(test_db):
    """Create a new user with profile_completed=False (simulating first-time user)."""
    user = User(id=1, timezone="UTC", current_streak=0, version=1, profile_completed=False)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def user_with_locale(test_db, new_user):
    """Create a user who has completed locale onboarding but not profile."""
    locale = UserLocale(
        user_id=new_user.id,
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
    return new_user


class TestOnboardingFlowEndToEnd:
    """Tests for the complete onboarding flow from new user to dashboard access."""

    def test_new_user_blocked_from_protected_routes(self, client, new_user):
        """New user with profile_completed=False should be blocked from protected routes."""
        # Transactions should be blocked
        response = client.get("/api/transactions")
        assert response.status_code == 403
        assert response.json()["detail"] == "Profile onboarding required"

        # Budgets should be blocked
        response = client.get("/api/budgets")
        assert response.status_code == 403

        # Dashboard should be blocked
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code == 403

    def test_locale_and_profile_endpoints_accessible_before_onboarding(self, client, new_user):
        """Locale and profile endpoints should be accessible even with incomplete profile."""
        # Profile endpoint should work (returns 404 because not set, not 403)
        response = client.get("/api/profile")
        assert response.status_code == 404

        # Settings locale should work
        response = client.get("/api/settings/locale")
        assert response.status_code != 403

    def test_locale_onboarding_sets_country(self, client, new_user):
        """PUT /api/settings/locale should set the user's locale config."""
        response = client.put(
            "/api/settings/locale",
            json={"country_code": "US"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["locale"]["currency_code"] == "USD"
        assert data["locale"]["currency_symbol"] == "$"

    def test_profile_submission_sets_profile_completed(self, client, user_with_locale, test_db):
        """PUT /api/profile should set profile_completed=True."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["profile_completed"] is True

        # Verify in DB
        test_db.refresh(user_with_locale)
        assert user_with_locale.profile_completed is True

    def test_profile_submission_triggers_weight_recomputation(self, client, user_with_locale, test_db):
        """PUT /api/profile should trigger CategoryWeightService.recompute_weights."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200

        # Check that weights were created
        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .all()
        )
        assert len(weights) >= 4  # At minimum: Savings, Wants, Transportation, Food

        # Verify category names
        category_names = {w.category_name for w in weights}
        assert "Savings" in category_names
        assert "Wants" in category_names
        assert "Transportation" in category_names
        assert "Food" in category_names

    def test_derived_weights_reflect_weight_rules_table(self, client, user_with_locale, test_db):
        """Derived weights should match the Weight_Rules_Table for (working, public_transit, None)."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200

        # Fetch weights from DB
        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .order_by(CategoryWeight.category_name)
            .all()
        )

        weight_map = {w.category_name: w.weight_percentage for w in weights}

        # Expected from WEIGHT_RULES_TABLE for ("working", "public_transit", None):
        assert weight_map["Savings"] == Decimal("30.00")
        assert weight_map["Wants"] == Decimal("25.00")
        assert weight_map["Transportation"] == Decimal("15.00")
        assert weight_map["Food"] == Decimal("30.00")

    def test_weights_sum_to_100(self, client, user_with_locale, test_db):
        """All derived weights must sum to exactly 100%."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "own_vehicle",
                "vehicle_type": "car",
            },
        )
        assert response.status_code == 200

        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .all()
        )

        total = sum(w.weight_percentage for w in weights)
        assert total == Decimal("100.00")

    def test_weights_not_manually_overridden_after_derivation(self, client, user_with_locale, test_db):
        """All newly derived weights should have is_manual_override=False."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "both",
                "commute_method": "walking_biking",
            },
        )
        assert response.status_code == 200

        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .all()
        )

        for w in weights:
            assert w.is_manual_override is False

    def test_dashboard_accessible_after_profile_completion(self, client, user_with_locale, test_db):
        """After profile completion, dashboard endpoints should be accessible."""
        # First, complete the profile
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200

        # Now dashboard should be accessible (not 403)
        response = client.get("/api/dashboard/summary?period=daily")
        assert response.status_code != 403

        # Budgets should be accessible
        response = client.get("/api/budgets")
        assert response.status_code != 403

        # Transactions should be accessible
        response = client.get("/api/transactions")
        assert response.status_code != 403

    def test_dashboard_insight_reflects_derived_weights(self, client, user_with_locale, test_db):
        """Dashboard insight should reference the highest-weight category after profile completion."""
        # Complete profile with working + none_remote → Savings=35%, Wants=30%, Transportation=5%, Food=30%
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "none_remote",
            },
        )
        assert response.status_code == 200

        # Get dashboard insight
        response = client.get("/api/dashboard/insight")
        assert response.status_code == 200
        data = response.json()

        # The highest weight for (working, none_remote) is Savings at 35%
        assert data["category_focus"] == "Savings"
        assert "Savings" in data["insight_text"]

    def test_full_flow_new_user_to_dashboard(self, client, test_db):
        """
        Complete end-to-end flow:
        1. Create user (profile_completed=False)
        2. Set locale
        3. Submit profile
        4. Verify dashboard access with derived weights
        """
        # Step 1: New user exists
        user = User(id=1, timezone="UTC", current_streak=0, version=1, profile_completed=False)
        test_db.add(user)
        test_db.commit()

        # Step 2: Protected routes are blocked
        response = client.get("/api/budgets")
        assert response.status_code == 403

        # Step 3: Set locale (exempt from gate)
        response = client.put(
            "/api/settings/locale",
            json={"country_code": "PH"},
        )
        assert response.status_code == 200
        assert response.json()["locale"]["currency_code"] == "PHP"

        # Step 4: Still blocked from protected routes
        response = client.get("/api/budgets")
        assert response.status_code == 403

        # Step 5: Submit profile
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200
        assert response.json()["profile_completed"] is True

        # Step 6: Protected routes are now accessible
        response = client.get("/api/budgets")
        assert response.status_code == 200

        # Step 7: Weights exist and sum to 100%
        response = client.get("/api/weights")
        assert response.status_code == 200
        data = response.json()
        assert len(data["weights"]) == 4
        assert Decimal(str(data["total_percentage"])) == Decimal("100.00")

        # Step 8: Verify weights match (student, public_transit, None)
        weight_map = {w["category_name"]: Decimal(str(w["weight_percentage"])) for w in data["weights"]}
        assert weight_map["Savings"] == Decimal("20.00")
        assert weight_map["Wants"] == Decimal("30.00")
        assert weight_map["Transportation"] == Decimal("15.00")
        assert weight_map["Food"] == Decimal("35.00")

        # Step 9: Dashboard insight is available
        response = client.get("/api/dashboard/insight")
        assert response.status_code == 200
        insight = response.json()
        # Food has highest weight (35%) for student + public_transit
        assert insight["category_focus"] == "Food"
        # Insight text should be present (may be a generic tip when no budgets exist)
        assert len(insight["insight_text"]) > 0

    def test_profile_update_triggers_weight_recomputation(self, client, user_with_locale, test_db):
        """Editing profile after initial onboarding should recompute weights."""
        # Initial profile submission
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200

        # Verify initial weights: (student, public_transit, None)
        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .all()
        )
        weight_map = {w.category_name: w.weight_percentage for w in weights}
        assert weight_map["Savings"] == Decimal("20.00")
        assert weight_map["Transportation"] == Decimal("15.00")

        # Update profile to a different combination
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "own_vehicle",
                "vehicle_type": "car",
            },
        )
        assert response.status_code == 200

        # Verify weights changed: (working, own_vehicle, car)
        test_db.expire_all()
        weights = (
            test_db.query(CategoryWeight)
            .filter(CategoryWeight.user_id == user_with_locale.id)
            .all()
        )
        weight_map = {w.category_name: w.weight_percentage for w in weights}
        assert weight_map["Savings"] == Decimal("20.00")
        assert weight_map["Transportation"] == Decimal("30.00")
