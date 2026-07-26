"""Tests for profile API endpoints and onboarding gate middleware.

Covers: GET /api/profile, PUT /api/profile, and the
ProfileOnboardingGateMiddleware that returns 403 for incomplete profiles.

Requirements covered: 15.1, 15.4, 15.5
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
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
def test_user(test_db):
    """Create a test user with profile_completed=False."""
    user = User(id=1, timezone="UTC", current_streak=0, version=1, profile_completed=False)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_user_with_profile(test_db):
    """Create a test user with profile_completed=True."""
    from app.models.user import CommuteMethod, EmploymentStatus

    user = User(
        id=1,
        timezone="UTC",
        current_streak=0,
        version=1,
        profile_completed=True,
        employment_status=EmploymentStatus.working,
        commute_method=CommuteMethod.public_transit,
        vehicle_type=None,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestGetProfile:
    """Tests for GET /api/profile."""

    def test_get_profile_not_set_returns_404(self, client, test_user):
        """Should return 404 when profile is not yet completed."""
        response = client.get("/api/profile")
        assert response.status_code == 404
        data = response.json()
        assert "Profile not set" in data["detail"]

    def test_get_profile_completed_returns_profile(self, client, test_user_with_profile):
        """Should return profile data when profile is completed."""
        response = client.get("/api/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["employment_status"] == "working"
        assert data["commute_method"] == "public_transit"
        assert data["vehicle_type"] is None
        assert data["profile_completed"] is True


class TestUpdateProfile:
    """Tests for PUT /api/profile."""

    def test_update_profile_creates_profile(self, client, test_user):
        """Should create profile and set profile_completed=True."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["employment_status"] == "student"
        assert data["commute_method"] == "public_transit"
        assert data["vehicle_type"] is None
        assert data["profile_completed"] is True

    def test_update_profile_with_vehicle_type(self, client, test_user):
        """Should accept vehicle_type when commute_method is own_vehicle."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "own_vehicle",
                "vehicle_type": "car",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["employment_status"] == "working"
        assert data["commute_method"] == "own_vehicle"
        assert data["vehicle_type"] == "car"
        assert data["profile_completed"] is True

    def test_update_profile_own_vehicle_without_type_returns_422(self, client, test_user):
        """Should return 422 when own_vehicle selected without vehicle_type."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "own_vehicle",
            },
        )
        assert response.status_code == 422

    def test_update_profile_invalid_employment_status_returns_422(self, client, test_user):
        """Should return 422 for invalid employment_status."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "retired",
                "commute_method": "public_transit",
            },
        )
        assert response.status_code == 422

    def test_update_profile_invalid_commute_method_returns_422(self, client, test_user):
        """Should return 422 for invalid commute_method."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "helicopter",
            },
        )
        assert response.status_code == 422

    def test_update_profile_updates_existing(self, client, test_user_with_profile):
        """Should update an existing profile."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "both",
                "commute_method": "walking_biking",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["employment_status"] == "both"
        assert data["commute_method"] == "walking_biking"
        assert data["vehicle_type"] is None

    def test_update_profile_vehicle_type_cleared_when_not_own_vehicle(self, client, test_user):
        """Should clear vehicle_type if commute_method is not own_vehicle."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "working",
                "commute_method": "public_transit",
                "vehicle_type": "car",  # Should be cleared by validator
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["vehicle_type"] is None


class TestProfileOnboardingGateMiddleware:
    """Tests for the profile onboarding gate middleware."""

    def test_middleware_blocks_protected_routes_when_profile_incomplete(self, client, test_user):
        """Should return 403 for non-exempt routes when profile_completed=False."""
        response = client.get("/api/budgets")
        assert response.status_code == 403
        data = response.json()
        assert data["detail"] == "Profile onboarding required"

    def test_middleware_allows_profile_route_when_incomplete(self, client, test_user):
        """Should allow access to /api/profile even when profile_completed=False."""
        response = client.get("/api/profile")
        # Should not be 403 - it returns 404 because profile isn't set, which is correct
        assert response.status_code != 403

    def test_middleware_allows_settings_locale_when_incomplete(self, client, test_user):
        """Should allow access to /api/settings/locale when profile_completed=False."""
        response = client.get("/api/settings/locale")
        # Should not be 403 - it returns 404 because locale isn't set, which is correct
        assert response.status_code != 403

    def test_middleware_allows_health_when_incomplete(self, client, test_user):
        """Should allow access to /health when profile_completed=False."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_middleware_allows_protected_routes_when_profile_complete(self, client, test_user_with_profile):
        """Should allow access to protected routes when profile_completed=True."""
        response = client.get("/api/budgets")
        assert response.status_code == 200

    def test_middleware_allows_when_no_user_exists(self, client):
        """Should allow access when no user exists (user not created yet)."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_middleware_blocks_transactions_when_incomplete(self, client, test_user):
        """Should return 403 for /api/transactions when profile_completed=False."""
        response = client.get("/api/transactions")
        assert response.status_code == 403
        assert response.json()["detail"] == "Profile onboarding required"

    def test_middleware_allows_put_profile_when_incomplete(self, client, test_user):
        """Should allow PUT /api/profile when profile_completed=False."""
        response = client.put(
            "/api/profile",
            json={
                "employment_status": "student",
                "commute_method": "none_remote",
            },
        )
        # Should succeed (not blocked by middleware)
        assert response.status_code == 200
