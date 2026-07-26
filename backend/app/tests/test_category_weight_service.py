"""Tests for CategoryWeightService.

Covers: derive_defaults, get_weights, recompute_weights, override_weight,
validate_weights, and edge cases.

Requirements validated: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.category_weight import CategoryWeight
from app.models.user import CommuteMethod, EmploymentStatus, User, VehicleType
from app.services.category_weight_service import (
    TARGET_SUM,
    WeightOverrideError,
    WeightValidationError,
    derive_defaults,
    get_weights,
    override_weight,
    recompute_weights,
    validate_weights,
)


def _create_test_session() -> Session:
    """Create an in-memory SQLite engine and session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    return TestSession()


def _create_user(
    db: Session,
    employment_status: EmploymentStatus | None = None,
    commute_method: CommuteMethod | None = None,
    vehicle_type: VehicleType | None = None,
    profile_completed: bool = False,
) -> User:
    """Helper to create a test user with profile fields."""
    user = User(
        timezone="UTC",
        current_streak=0,
        streak_last_updated_utc=None,
        created_at_utc=datetime.now(timezone.utc),
        version=1,
        employment_status=employment_status,
        commute_method=commute_method,
        vehicle_type=vehicle_type,
        profile_completed=profile_completed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_weights(
    db: Session, user_id: int, weights: dict[str, Decimal], overrides: set[str] | None = None
) -> list[CategoryWeight]:
    """Helper to create CategoryWeight entries for a user."""
    if overrides is None:
        overrides = set()
    result = []
    for category_name, percentage in weights.items():
        cw = CategoryWeight(
            user_id=user_id,
            category_name=category_name,
            weight_percentage=percentage,
            is_manual_override=category_name in overrides,
        )
        db.add(cw)
        result.append(cw)
    db.commit()
    for cw in result:
        db.refresh(cw)
    return result


class TestDeriveDefaults:
    """Tests for derive_defaults (pure function, Req 16.3)."""

    def test_student_public_transit(self):
        """Known profile should return exact weights from rules table."""
        result = derive_defaults("student", "public_transit", None)
        assert result == {
            "Savings": Decimal("20.00"),
            "Wants": Decimal("30.00"),
            "Transportation": Decimal("15.00"),
            "Food": Decimal("35.00"),
        }
        assert sum(result.values()) == TARGET_SUM

    def test_working_own_vehicle_car(self):
        """Working with car should return correct weights."""
        result = derive_defaults("working", "own_vehicle", "car")
        assert result == {
            "Savings": Decimal("20.00"),
            "Wants": Decimal("20.00"),
            "Transportation": Decimal("30.00"),
            "Food": Decimal("30.00"),
        }
        assert sum(result.values()) == TARGET_SUM

    def test_unknown_profile_returns_fallback(self):
        """Unknown profile combination should return equal distribution."""
        result = derive_defaults("unknown", "unknown", None)
        assert sum(result.values()) == TARGET_SUM
        # All values should be equal (fallback)
        values = list(result.values())
        assert all(v == values[0] for v in values)

    def test_none_profile_uses_defaults(self):
        """None profile values should use working/none_remote defaults."""
        result = derive_defaults(None, None, None)
        assert sum(result.values()) == TARGET_SUM

    def test_all_profiles_sum_to_100(self):
        """Every valid profile combination should sum to exactly 100."""
        profiles = [
            ("student", "public_transit", None),
            ("student", "own_vehicle", "motorcycle"),
            ("student", "own_vehicle", "car"),
            ("student", "walking_biking", None),
            ("student", "none_remote", None),
            ("working", "public_transit", None),
            ("working", "own_vehicle", "motorcycle"),
            ("working", "own_vehicle", "car"),
            ("working", "walking_biking", None),
            ("working", "none_remote", None),
            ("both", "public_transit", None),
            ("both", "own_vehicle", "motorcycle"),
            ("both", "own_vehicle", "car"),
            ("both", "walking_biking", None),
            ("both", "none_remote", None),
        ]
        for emp, commute, vehicle in profiles:
            result = derive_defaults(emp, commute, vehicle)
            assert sum(result.values()) == TARGET_SUM, f"Failed for {emp}, {commute}, {vehicle}"


class TestValidateWeights:
    """Tests for validate_weights (Req 16.6)."""

    def test_valid_sum_passes(self):
        """Weights summing to 100 should pass validation."""
        db = _create_test_session()
        user = _create_user(db)
        weights = _create_weights(db, user.id, {
            "Savings": Decimal("25.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })
        assert validate_weights(weights) is True

    def test_invalid_sum_raises_error(self):
        """Weights not summing to 100 should raise WeightValidationError."""
        db = _create_test_session()
        user = _create_user(db)
        weights = _create_weights(db, user.id, {
            "Savings": Decimal("30.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })
        with pytest.raises(WeightValidationError):
            validate_weights(weights)


class TestGetWeights:
    """Tests for get_weights."""

    def test_returns_all_weights_for_user(self):
        """Should return all CategoryWeight entries for the specified user."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Savings": Decimal("25.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })
        result = get_weights(db, user.id)
        assert len(result) == 4

    def test_returns_empty_for_no_weights(self):
        """Should return empty list when user has no weights."""
        db = _create_test_session()
        user = _create_user(db)
        result = get_weights(db, user.id)
        assert result == []

    def test_weights_sorted_by_category_name(self):
        """Should return weights sorted alphabetically by category name."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Wants": Decimal("25.00"),
            "Food": Decimal("25.00"),
            "Savings": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
        })
        result = get_weights(db, user.id)
        names = [w.category_name for w in result]
        assert names == sorted(names)


class TestRecomputeWeights:
    """Tests for recompute_weights (Req 16.3, 16.4, 16.5)."""

    def test_creates_weights_for_new_user(self):
        """User with no existing weights gets defaults from profile."""
        db = _create_test_session()
        user = _create_user(
            db,
            employment_status=EmploymentStatus.student,
            commute_method=CommuteMethod.public_transit,
        )
        result = recompute_weights(db, user.id)
        assert len(result) == 4
        total = sum(w.weight_percentage for w in result)
        assert total == TARGET_SUM
        # All should be non-manual
        assert all(not w.is_manual_override for w in result)

    def test_preserves_manual_overrides(self):
        """Manual overrides should be preserved during recomputation."""
        db = _create_test_session()
        user = _create_user(
            db,
            employment_status=EmploymentStatus.working,
            commute_method=CommuteMethod.public_transit,
        )
        # Create initial weights with a manual override on Savings
        _create_weights(
            db, user.id,
            {
                "Savings": Decimal("40.00"),
                "Wants": Decimal("20.00"),
                "Transportation": Decimal("15.00"),
                "Food": Decimal("25.00"),
            },
            overrides={"Savings"},
        )

        result = recompute_weights(db, user.id)
        total = sum(w.weight_percentage for w in result)
        assert total == TARGET_SUM

        # Savings should remain at 40% (manually overridden)
        savings = next(w for w in result if w.category_name == "Savings")
        assert savings.weight_percentage == Decimal("40.00")
        assert savings.is_manual_override is True

        # Others should be redistributed to fill remaining 60%
        others = [w for w in result if w.category_name != "Savings"]
        others_total = sum(w.weight_percentage for w in others)
        assert others_total == Decimal("60.00")

    def test_user_not_found_raises_error(self):
        """Should raise ValueError for non-existent user."""
        db = _create_test_session()
        with pytest.raises(ValueError, match="User with id 999 not found"):
            recompute_weights(db, 999)

    def test_profile_change_updates_non_manual_weights(self):
        """Changing profile should update non-manual weights."""
        db = _create_test_session()
        user = _create_user(
            db,
            employment_status=EmploymentStatus.student,
            commute_method=CommuteMethod.public_transit,
        )
        # Initial computation
        recompute_weights(db, user.id)

        # Change profile
        user.employment_status = EmploymentStatus.working
        user.commute_method = CommuteMethod.own_vehicle
        user.vehicle_type = VehicleType.car
        db.commit()

        # Recompute
        result = recompute_weights(db, user.id)
        total = sum(w.weight_percentage for w in result)
        assert total == TARGET_SUM

        # Should now reflect working + car profile
        transportation = next(w for w in result if w.category_name == "Transportation")
        assert transportation.weight_percentage == Decimal("30.00")


class TestOverrideWeight:
    """Tests for override_weight (Req 16.5, 16.6, 16.7)."""

    def test_basic_override(self):
        """Overriding one category redistributes others proportionally."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Savings": Decimal("25.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })

        result = override_weight(db, user.id, "Savings", Decimal("40.00"))
        total = sum(w.weight_percentage for w in result)
        assert total == TARGET_SUM

        savings = next(w for w in result if w.category_name == "Savings")
        assert savings.weight_percentage == Decimal("40.00")
        assert savings.is_manual_override is True

        # Others should share remaining 60% equally (since they were all 25%)
        others = [w for w in result if w.category_name != "Savings"]
        for w in others:
            assert w.weight_percentage == Decimal("20.00")

    def test_override_with_existing_manual(self):
        """Override with another category already manual should still work."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(
            db, user.id,
            {
                "Savings": Decimal("40.00"),
                "Wants": Decimal("20.00"),
                "Transportation": Decimal("20.00"),
                "Food": Decimal("20.00"),
            },
            overrides={"Savings"},
        )

        result = override_weight(db, user.id, "Food", Decimal("30.00"))
        total = sum(w.weight_percentage for w in result)
        assert total == TARGET_SUM

        # Savings stays at 40 (manual), Food becomes 30 (manual)
        savings = next(w for w in result if w.category_name == "Savings")
        food = next(w for w in result if w.category_name == "Food")
        assert savings.weight_percentage == Decimal("40.00")
        assert food.weight_percentage == Decimal("30.00")
        assert food.is_manual_override is True

        # Remaining 30% shared by Wants and Transportation
        non_manual = [w for w in result if not w.is_manual_override]
        non_manual_total = sum(w.weight_percentage for w in non_manual)
        assert non_manual_total == Decimal("30.00")

    def test_all_others_manual_raises_422_error(self):
        """When all other categories are manually overridden, should raise error."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(
            db, user.id,
            {
                "Savings": Decimal("30.00"),
                "Wants": Decimal("30.00"),
                "Transportation": Decimal("20.00"),
                "Food": Decimal("20.00"),
            },
            overrides={"Wants", "Transportation", "Food"},
        )

        with pytest.raises(WeightOverrideError, match="all other categories are already manually overridden"):
            override_weight(db, user.id, "Savings", Decimal("50.00"))

    def test_invalid_percentage_raises_error(self):
        """Percentage outside 0-100 should raise error."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Savings": Decimal("25.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })

        with pytest.raises(WeightOverrideError):
            override_weight(db, user.id, "Savings", Decimal("150.00"))

        with pytest.raises(WeightOverrideError):
            override_weight(db, user.id, "Savings", Decimal("-5.00"))

    def test_category_not_found_raises_error(self):
        """Override for non-existent category should raise ValueError."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Savings": Decimal("25.00"),
            "Wants": Decimal("25.00"),
            "Transportation": Decimal("25.00"),
            "Food": Decimal("25.00"),
        })

        with pytest.raises(ValueError, match="Category 'Entertainment' not found"):
            override_weight(db, user.id, "Entertainment", Decimal("10.00"))

    def test_no_weights_raises_error(self):
        """Override with no existing weights should raise ValueError."""
        db = _create_test_session()
        user = _create_user(db)

        with pytest.raises(ValueError, match="No category weights found"):
            override_weight(db, user.id, "Savings", Decimal("50.00"))

    def test_override_exceeds_available_raises_error(self):
        """Override that leaves insufficient room for manual others should error."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(
            db, user.id,
            {
                "Savings": Decimal("25.00"),
                "Wants": Decimal("60.00"),
                "Transportation": Decimal("10.00"),
                "Food": Decimal("5.00"),
            },
            overrides={"Wants"},
        )

        # Wants is 60% manual, trying to set Savings to 50% leaves -10% for others
        with pytest.raises(WeightOverrideError, match="Cannot set Savings to"):
            override_weight(db, user.id, "Savings", Decimal("50.00"))

    def test_sum_always_100_after_override(self):
        """Sum should always be exactly 100 after any valid override."""
        db = _create_test_session()
        user = _create_user(db)
        _create_weights(db, user.id, {
            "Savings": Decimal("20.00"),
            "Wants": Decimal("30.00"),
            "Transportation": Decimal("15.00"),
            "Food": Decimal("35.00"),
        })

        # Multiple overrides in sequence
        result = override_weight(db, user.id, "Food", Decimal("40.00"))
        assert sum(w.weight_percentage for w in result) == TARGET_SUM

        result = override_weight(db, user.id, "Savings", Decimal("10.00"))
        assert sum(w.weight_percentage for w in result) == TARGET_SUM
