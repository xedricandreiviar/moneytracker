"""Tests for SQLAlchemy ORM models."""

from datetime import date, datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Budget,
    BudgetPeriodRecord,
    BudgetPeriodStatus,
    BudgetPeriodType,
    Category,
    CoachingSuggestion,
    CoachingSuggestionStatus,
    DailyTask,
    DailyTaskCompletionType,
    DailyTaskStatus,
    Notification,
    SpikeSuppression,
    Transaction,
    TransactionDirection,
    User,
    UserLocale,
)


def get_test_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


class TestModelsExist:
    """Verify all models are registered in Base metadata."""

    def test_all_tables_registered(self):
        """All expected tables should be in Base.metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "users",
            "user_locales",
            "transactions",
            "categories",
            "daily_tasks",
            "budgets",
            "budget_period_records",
            "notifications",
            "spike_suppressions",
            "coaching_suggestions",
        }
        assert expected.issubset(table_names), (
            f"Missing tables: {expected - table_names}"
        )


class TestUserModel:
    """User model tests."""

    def test_user_creation(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="America/New_York",
                current_streak=5,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            assert user.id is not None
            assert user.timezone == "America/New_York"
            assert user.current_streak == 5
            assert user.version == 1

    def test_user_version_column_for_optimistic_locking(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            # Simulate optimistic lock update
            user.current_streak = 1
            user.version = 2
            session.commit()
            session.refresh(user)

            assert user.current_streak == 1
            assert user.version == 2


class TestUserLocaleModel:
    """UserLocale model tests."""

    def test_user_locale_creation(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            locale = UserLocale(
                user_id=user.id,
                country_code="US",
                currency_code="USD",
                currency_symbol="$",
                decimal_precision=2,
                decimal_separator=".",
                thousands_separator=",",
                date_format="MM/DD/YYYY",
                week_start_day=0,
                updated_at_utc=datetime.utcnow(),
            )
            session.add(locale)
            session.commit()
            session.refresh(locale)

            assert locale.currency_code == "USD"
            assert locale.decimal_precision == 2
            assert locale.week_start_day == 0


class TestTransactionModel:
    """Transaction model tests."""

    def test_transaction_stores_amount_as_integer(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            txn = Transaction(
                user_id=user.id,
                amount_smallest_unit=1050,  # $10.50 in cents
                direction=TransactionDirection.spent,
                currency_code="USD",
                transaction_datetime_utc=datetime.utcnow(),
                transaction_date_local=date.today(),
                created_at_utc=datetime.utcnow(),
            )
            session.add(txn)
            session.commit()
            session.refresh(txn)

            assert txn.amount_smallest_unit == 1050
            assert txn.currency_code == "USD"
            assert txn.direction == TransactionDirection.spent

    def test_transaction_with_category(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            cat = Category(user_id=user.id, name="Food", usage_count=3)
            session.add(cat)
            session.commit()

            txn = Transaction(
                user_id=user.id,
                amount_smallest_unit=500,
                direction=TransactionDirection.spent,
                currency_code="USD",
                category_id=cat.id,
                note="Lunch",
                transaction_datetime_utc=datetime.utcnow(),
                transaction_date_local=date.today(),
                created_at_utc=datetime.utcnow(),
            )
            session.add(txn)
            session.commit()
            session.refresh(txn)

            assert txn.category_id == cat.id
            assert txn.note == "Lunch"


class TestDailyTaskModel:
    """DailyTask model tests."""

    def test_daily_task_enums(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            task = DailyTask(
                user_id=user.id,
                task_date=date.today(),
                status=DailyTaskStatus.pending,
                created_at_utc=datetime.utcnow(),
            )
            session.add(task)
            session.commit()

            # Complete via transaction
            task.status = DailyTaskStatus.completed
            task.completion_type = DailyTaskCompletionType.transaction_logged
            task.completed_at_utc = datetime.utcnow()
            session.commit()
            session.refresh(task)

            assert task.status == DailyTaskStatus.completed
            assert task.completion_type == DailyTaskCompletionType.transaction_logged

    def test_daily_task_status_values(self):
        assert DailyTaskStatus.pending.value == "pending"
        assert DailyTaskStatus.completed.value == "completed"
        assert DailyTaskStatus.missed.value == "missed"
        assert DailyTaskStatus.grace_period.value == "grace_period"

    def test_daily_task_completion_type_values(self):
        assert DailyTaskCompletionType.transaction_logged.value == "transaction_logged"
        assert DailyTaskCompletionType.no_transactions.value == "no_transactions"
        assert DailyTaskCompletionType.grace_recovery.value == "grace_recovery"


class TestBudgetModel:
    """Budget and BudgetPeriodRecord model tests."""

    def test_budget_period_type_enum(self):
        assert BudgetPeriodType.weekly.value == "weekly"
        assert BudgetPeriodType.monthly.value == "monthly"

    def test_budget_creation(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            budget = Budget(
                user_id=user.id,
                category_id=None,  # Overall budget
                period_type=BudgetPeriodType.monthly,
                limit_smallest_unit=100000,  # $1000.00
                currency_code="USD",
                is_active=True,
                created_at_utc=datetime.utcnow(),
            )
            session.add(budget)
            session.commit()
            session.refresh(budget)

            assert budget.category_id is None
            assert budget.limit_smallest_unit == 100000
            assert budget.is_active is True

    def test_budget_period_record(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            budget = Budget(
                user_id=user.id,
                period_type=BudgetPeriodType.weekly,
                limit_smallest_unit=50000,
                currency_code="USD",
                is_active=True,
                created_at_utc=datetime.utcnow(),
            )
            session.add(budget)
            session.commit()

            record = BudgetPeriodRecord(
                budget_id=budget.id,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 1, 7),
                spent_smallest_unit=25000,
                status=BudgetPeriodStatus.active,
            )
            session.add(record)
            session.commit()
            session.refresh(record)

            assert record.spent_smallest_unit == 25000
            assert record.status == BudgetPeriodStatus.active


class TestCoachingSuggestionModel:
    """CoachingSuggestion model tests."""

    def test_coaching_suggestion_status_enum(self):
        assert CoachingSuggestionStatus.pending.value == "pending"
        assert CoachingSuggestionStatus.accepted.value == "accepted"
        assert CoachingSuggestionStatus.dismissed.value == "dismissed"

    def test_coaching_suggestion_creation(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            budget = Budget(
                user_id=user.id,
                period_type=BudgetPeriodType.monthly,
                limit_smallest_unit=100000,
                currency_code="USD",
                is_active=True,
                created_at_utc=datetime.utcnow(),
            )
            session.add(budget)
            session.commit()

            suggestion = CoachingSuggestion(
                user_id=user.id,
                budget_id=budget.id,
                suggestion_text="You're spending 35% more than expected on Food.",
                deviation_percentage=35.0,
                status=CoachingSuggestionStatus.pending,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 1, 31),
                created_at_utc=datetime.utcnow(),
            )
            session.add(suggestion)
            session.commit()
            session.refresh(suggestion)

            assert suggestion.deviation_percentage == 35.0
            assert suggestion.status == CoachingSuggestionStatus.pending


class TestSpikeSuppression:
    """SpikeSuppression model tests."""

    def test_spike_suppression_creation(self):
        engine = get_test_engine()
        with Session(engine) as session:
            user = User(
                timezone="UTC",
                current_streak=0,
                created_at_utc=datetime.utcnow(),
                version=1,
            )
            session.add(user)
            session.commit()

            cat = Category(user_id=user.id, name="Dining", usage_count=10)
            session.add(cat)
            session.commit()

            suppression = SpikeSuppression(
                user_id=user.id,
                category_id=cat.id,
                week_start=date(2024, 1, 1),
                week_end=date(2024, 1, 7),
                created_at_utc=datetime.utcnow(),
            )
            session.add(suppression)
            session.commit()
            session.refresh(suppression)

            assert suppression.week_start == date(2024, 1, 1)
            assert suppression.week_end == date(2024, 1, 7)


class TestTableIndexes:
    """Verify important indexes exist on tables."""

    def test_transactions_has_user_id_index(self):
        engine = get_test_engine()
        inspector = inspect(engine)
        indexes = inspector.get_indexes("transactions")
        index_cols = [idx["column_names"] for idx in indexes]
        assert ["user_id"] in index_cols

    def test_daily_tasks_has_user_date_index(self):
        engine = get_test_engine()
        inspector = inspect(engine)
        indexes = inspector.get_indexes("daily_tasks")
        index_cols = [idx["column_names"] for idx in indexes]
        assert ["user_id", "task_date"] in index_cols

    def test_notifications_has_user_id_index(self):
        engine = get_test_engine()
        inspector = inspect(engine)
        indexes = inspector.get_indexes("notifications")
        index_cols = [idx["column_names"] for idx in indexes]
        assert ["user_id"] in index_cols
