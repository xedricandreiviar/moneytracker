"""Tests for CoachingService.

Covers: deviation calculation, midpoint detection, dismiss logic with
re-surfacing threshold, multiple budget handling, and CoachingSuggestion
record creation.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.budget import (
    Budget,
    BudgetPeriodRecord,
    BudgetPeriodStatus,
    BudgetPeriodType,
)
from app.models.coaching_suggestion import CoachingSuggestion, CoachingSuggestionStatus
from app.models.user import User
from app.services.coaching_service import (
    _calculate_deviation,
    _should_resurface,
    accept_suggestion,
    dismiss_suggestion,
    get_pending_suggestions,
    get_proactive_coaching,
)


def _create_test_session():
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


def _create_budget_with_period(
    db: Session,
    user: User,
    limit: int = 100000,
    period_type: BudgetPeriodType = BudgetPeriodType.monthly,
    period_start: date = date(2024, 3, 1),
    period_end: date = date(2024, 3, 31),
    spent: int = 0,
) -> tuple[Budget, BudgetPeriodRecord]:
    """Helper to create a budget with an active period record."""
    budget = Budget(
        user_id=user.id,
        period_type=period_type,
        limit_smallest_unit=limit,
        currency_code="USD",
        is_active=True,
    )
    db.add(budget)
    db.flush()

    period = BudgetPeriodRecord(
        budget_id=budget.id,
        period_start=period_start,
        period_end=period_end,
        spent_smallest_unit=spent,
        status=BudgetPeriodStatus.active,
    )
    db.add(period)
    db.commit()
    db.refresh(budget)
    db.refresh(period)
    return budget, period


class TestDeviationCalculation:
    """Tests for budget deviation calculation (Req 10.1)."""

    def test_no_deviation_before_midpoint(self):
        """Should return None before the midpoint of the period."""
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000, currency_code="USD", is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31), spent_smallest_unit=60000,
            status=BudgetPeriodStatus.active,
        )
        # Day 10 of 31: not at midpoint (midpoint = 15.5)
        result = _calculate_deviation(budget, period, today=date(2024, 3, 10))
        assert result is None

    def test_deviation_detected_at_midpoint(self):
        """Should detect deviation at the midpoint (Req 10.1).

        Monthly budget: 100000, 31 days total.
        At day 16 (midpoint): pro-rated = (100000/31)*16 = 51612
        Actual spend: 70000 -> deviation = (70000-51612)/51612 = 35.6%
        """
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000, currency_code="USD", is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31), spent_smallest_unit=70000,
            status=BudgetPeriodStatus.active,
        )
        # Day 16 of 31: at midpoint
        result = _calculate_deviation(budget, period, today=date(2024, 3, 16))
        assert result is not None
        assert result.deviation_percentage > 20.0
        assert result.actual_spent == 70000
        assert result.days_elapsed == 16
        assert result.total_days == 31

    def test_no_deviation_when_within_20_percent(self):
        """Should return None when deviation is <= 20% (Req 10.1).

        Monthly budget: 100000, 31 days.
        At day 16: pro-rated = (100000/31)*16 = 51612
        Actual spend: 55000 -> deviation = (55000-51612)/51612 = 6.6%
        """
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000, currency_code="USD", is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31), spent_smallest_unit=55000,
            status=BudgetPeriodStatus.active,
        )
        result = _calculate_deviation(budget, period, today=date(2024, 3, 16))
        assert result is None

    def test_underspending_deviation_detected(self):
        """Should detect under-spending deviation > 20%.

        Monthly budget: 100000, 31 days.
        At day 16: pro-rated = (100000/31)*16 = 51612
        Actual spend: 30000 -> deviation = |30000-51612|/51612 = 41.8%
        """
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000, currency_code="USD", is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31), spent_smallest_unit=30000,
            status=BudgetPeriodStatus.active,
        )
        result = _calculate_deviation(budget, period, today=date(2024, 3, 16))
        assert result is not None
        assert result.deviation_percentage > 20.0
        assert result.deviation_amount < 0  # underspending

    def test_weekly_budget_midpoint(self):
        """Should check at midpoint of weekly budget.

        Weekly budget: 7000, 7 days.
        At day 4 (midpoint = 3.5): pro-rated = (7000/7)*4 = 4000
        Actual spend: 5500 -> deviation = |5500-4000|/4000 = 37.5%
        """
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.weekly,
            limit_smallest_unit=7000, currency_code="USD", is_active=True,
        )
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 10),
            period_end=date(2024, 3, 16), spent_smallest_unit=5500,
            status=BudgetPeriodStatus.active,
        )
        # Day 4 of 7: at midpoint
        result = _calculate_deviation(budget, period, today=date(2024, 3, 13))
        assert result is not None
        assert result.deviation_percentage > 20.0

    def test_exactly_20_percent_deviation_not_flagged(self):
        """Exactly 20% deviation should NOT be flagged (> 20% required).

        Monthly budget: 100000, 31 days.
        At day 16: pro-rated = int((100000/31)*16) = 51612
        Need spend where |actual - 51612| / 51612 == 0.20 exactly
        actual = 51612 * 1.20 = 61934
        """
        budget = Budget(
            id=1, user_id=1, period_type=BudgetPeriodType.monthly,
            limit_smallest_unit=100000, currency_code="USD", is_active=True,
        )
        pro_rated = int((100000 / 31) * 16)
        # Set spend to exactly 20% over
        spend_at_20 = int(pro_rated * 1.20)
        period = BudgetPeriodRecord(
            id=1, budget_id=1, period_start=date(2024, 3, 1),
            period_end=date(2024, 3, 31), spent_smallest_unit=spend_at_20,
            status=BudgetPeriodStatus.active,
        )
        result = _calculate_deviation(budget, period, today=date(2024, 3, 16))
        # Exactly at boundary - due to integer math, this may be just at or just over
        # The point is: <= 20% returns None
        if result is not None:
            assert result.deviation_percentage > 20.0


class TestResurfaceLogic:
    """Tests for dismiss/re-surface threshold logic (Req 10.5)."""

    def test_should_not_resurface_below_threshold(self):
        """Should NOT re-surface when deviation hasn't increased by 10+ pp."""
        dismissed = CoachingSuggestion(
            id=1, user_id=1, budget_id=1,
            suggestion_text="test", deviation_percentage=25.0,
            status=CoachingSuggestionStatus.dismissed,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
        )
        # Current deviation is 30% (only 5pp increase, need 10+)
        assert _should_resurface(dismissed, 30.0) is False

    def test_should_resurface_at_threshold(self):
        """Should re-surface when deviation increases by exactly 10pp."""
        dismissed = CoachingSuggestion(
            id=1, user_id=1, budget_id=1,
            suggestion_text="test", deviation_percentage=25.0,
            status=CoachingSuggestionStatus.dismissed,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
        )
        # Current deviation is 35% (exactly 10pp increase)
        assert _should_resurface(dismissed, 35.0) is True

    def test_should_resurface_above_threshold(self):
        """Should re-surface when deviation increases by more than 10pp."""
        dismissed = CoachingSuggestion(
            id=1, user_id=1, budget_id=1,
            suggestion_text="test", deviation_percentage=25.0,
            status=CoachingSuggestionStatus.dismissed,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
        )
        # Current deviation is 50% (25pp increase)
        assert _should_resurface(dismissed, 50.0) is True

    def test_should_not_resurface_at_same_deviation(self):
        """Should NOT re-surface when deviation is the same."""
        dismissed = CoachingSuggestion(
            id=1, user_id=1, budget_id=1,
            suggestion_text="test", deviation_percentage=30.0,
            status=CoachingSuggestionStatus.dismissed,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
        )
        assert _should_resurface(dismissed, 30.0) is False


class TestGetProactiveCoaching:
    """Integration tests for get_proactive_coaching (Req 10.1-10.5)."""

    def test_generates_suggestion_for_deviating_budget(self):
        """Should create a CoachingSuggestion when deviation > 20% at midpoint."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))

        assert len(results) == 1
        assert results[0].suggestion.budget_id == budget.id
        assert results[0].suggestion.status == CoachingSuggestionStatus.pending
        assert results[0].suggestion.deviation_percentage > 20.0
        assert results[0].suggestion.user_id == user.id
        assert results[0].suggestion.period_start == date(2024, 3, 1)
        assert results[0].suggestion.period_end == date(2024, 3, 31)
        db.close()

    def test_no_suggestion_when_on_track(self):
        """Should not generate a suggestion when deviation <= 20%."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=55000,  # ~6.6% deviation at day 16
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 0
        db.close()

    def test_no_suggestion_before_midpoint(self):
        """Should not generate a suggestion before the midpoint."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,  # Would deviate, but too early
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 10))
        assert len(results) == 0
        db.close()

    def test_multiple_budgets_get_separate_suggestions(self):
        """Each deviating budget gets its own suggestion (Req 10.4)."""
        db = _create_test_session()
        user = _create_user(db)

        # Budget 1: monthly, deviating
        budget1, _ = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )
        # Budget 2: weekly, deviating
        budget2, _ = _create_budget_with_period(
            db, user, limit=7000,
            period_type=BudgetPeriodType.weekly,
            period_start=date(2024, 3, 10), period_end=date(2024, 3, 16),
            spent=5500,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))

        assert len(results) == 2
        budget_ids = {r.suggestion.budget_id for r in results}
        assert budget1.id in budget_ids
        assert budget2.id in budget_ids
        db.close()

    def test_does_not_duplicate_pending_suggestion(self):
        """Should not create a new suggestion if a pending one exists."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        # First call creates suggestion
        results1 = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results1) == 1

        # Second call should not duplicate
        results2 = get_proactive_coaching(db, user.id, today=date(2024, 3, 17))
        assert len(results2) == 0
        db.close()

    def test_dismissed_suggestion_not_resurfaced_below_threshold(self):
        """Dismissed suggestion should NOT re-surface if deviation < +10pp (Req 10.5)."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        # Generate and dismiss suggestion
        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1
        dismiss_suggestion(db, results[0].suggestion.id, user.id)

        # Slightly increase spending but not enough to re-surface
        period.spent_smallest_unit = 72000
        db.commit()

        results2 = get_proactive_coaching(db, user.id, today=date(2024, 3, 17))
        assert len(results2) == 0
        db.close()

    def test_dismissed_suggestion_resurfaced_above_threshold(self):
        """Dismissed suggestion SHOULD re-surface when deviation increases 10+ pp (Req 10.5)."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        # Generate and dismiss suggestion
        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1
        original_deviation = results[0].suggestion.deviation_percentage
        dismiss_suggestion(db, results[0].suggestion.id, user.id)

        # Significantly increase spending to push deviation 10+ pp higher
        # At day 20: pro-rated = (100000/31)*20 = 64516
        # Need actual to deviate by original_deviation + 10 pp
        # Target deviation >= original_deviation + 10
        # actual / pro_rated > 1 + (original_deviation + 10)/100
        target_deviation_fraction = (original_deviation + 10.0) / 100.0
        pro_rated_day20 = int((100000 / 31) * 20)
        needed_spend = int(pro_rated_day20 * (1 + target_deviation_fraction)) + 1
        period.spent_smallest_unit = needed_spend
        db.commit()

        results2 = get_proactive_coaching(db, user.id, today=date(2024, 3, 20))
        assert len(results2) == 1
        assert results2[0].suggestion.deviation_percentage > original_deviation + 10.0
        db.close()

    def test_accepted_suggestion_not_resurfaced(self):
        """Accepted suggestion should never re-surface."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        # Generate and accept
        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1
        accept_suggestion(db, results[0].suggestion.id, user.id)

        # Even with higher spending, accepted suggestions aren't resurfaced
        period.spent_smallest_unit = 95000
        db.commit()

        results2 = get_proactive_coaching(db, user.id, today=date(2024, 3, 20))
        assert len(results2) == 0
        db.close()

    def test_inactive_budget_ignored(self):
        """Inactive budgets should not generate suggestions."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )
        budget.is_active = False
        db.commit()

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 0
        db.close()

    def test_no_active_period_record(self):
        """Budget without active period record should be skipped."""
        db = _create_test_session()
        user = _create_user(db)
        budget, period = _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )
        period.status = BudgetPeriodStatus.completed
        db.commit()

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 0
        db.close()


class TestSuggestionText:
    """Tests for suggestion text generation (Req 10.2)."""

    def test_overspending_suggestion_includes_reasoning(self):
        """Suggestion text should include deviation, pro-rated, and amounts."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1

        text = results[0].suggestion.suggestion_text
        assert "over" in text.lower()
        assert "pro-rated" in text.lower()
        assert "deviation" in text.lower()
        # Contains actual numbers
        assert "70000" in text
        db.close()

    def test_underspending_suggestion_text(self):
        """Underspending suggestion should mention being under budget."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=30000,  # Significantly under budget
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1

        text = results[0].suggestion.suggestion_text
        assert "under" in text.lower()
        db.close()


class TestDismissAndAccept:
    """Tests for dismiss and accept functionality (Req 10.3)."""

    def test_dismiss_sets_status_and_timestamp(self):
        """Dismissing should set status to dismissed and record timestamp."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        suggestion = results[0].suggestion

        dismissed = dismiss_suggestion(db, suggestion.id, user.id)
        assert dismissed is not None
        assert dismissed.status == CoachingSuggestionStatus.dismissed
        assert dismissed.dismissed_at_utc is not None
        db.close()

    def test_accept_sets_status(self):
        """Accepting should set status to accepted."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        suggestion = results[0].suggestion

        accepted = accept_suggestion(db, suggestion.id, user.id)
        assert accepted is not None
        assert accepted.status == CoachingSuggestionStatus.accepted
        db.close()

    def test_dismiss_wrong_user_returns_none(self):
        """Cannot dismiss another user's suggestion."""
        db = _create_test_session()
        user1 = _create_user(db)
        user2 = _create_user(db)
        _create_budget_with_period(
            db, user1, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user1.id, today=date(2024, 3, 16))
        suggestion = results[0].suggestion

        dismissed = dismiss_suggestion(db, suggestion.id, user2.id)
        assert dismissed is None
        db.close()

    def test_dismiss_already_dismissed_returns_none(self):
        """Cannot dismiss an already-dismissed suggestion."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        suggestion = results[0].suggestion

        dismiss_suggestion(db, suggestion.id, user.id)
        # Second dismiss should fail (already dismissed)
        result = dismiss_suggestion(db, suggestion.id, user.id)
        assert result is None
        db.close()


class TestGetPendingSuggestions:
    """Tests for retrieving pending suggestions."""

    def test_get_pending_returns_only_pending(self):
        """Should only return suggestions with pending status."""
        db = _create_test_session()
        user = _create_user(db)
        _create_budget_with_period(
            db, user, limit=100000,
            period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
            spent=70000,
        )

        results = get_proactive_coaching(db, user.id, today=date(2024, 3, 16))
        assert len(results) == 1

        pending = get_pending_suggestions(db, user.id)
        assert len(pending) == 1
        assert pending[0].status == CoachingSuggestionStatus.pending

        # Dismiss it
        dismiss_suggestion(db, pending[0].id, user.id)

        pending_after = get_pending_suggestions(db, user.id)
        assert len(pending_after) == 0
        db.close()

    def test_get_pending_empty_for_new_user(self):
        """New user with no suggestions should get empty list."""
        db = _create_test_session()
        user = _create_user(db)

        pending = get_pending_suggestions(db, user.id)
        assert len(pending) == 0
        db.close()
