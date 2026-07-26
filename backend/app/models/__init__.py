"""SQLAlchemy ORM models for Daily Money Tracker.

All models are imported here to ensure they are registered with the
SQLAlchemy Base metadata, which is required for Alembic autogenerate.
"""

from app.models.budget import Budget, BudgetPeriodRecord, BudgetPeriodStatus, BudgetPeriodType
from app.models.budget_limit_change_log import BudgetLimitChangeLog
from app.models.category import Category
from app.models.category_override import CategoryOverride
from app.models.category_weight import CategoryWeight
from app.models.coaching_suggestion import CoachingSuggestion, CoachingSuggestionStatus
from app.models.daily_task import DailyTask, DailyTaskCompletionType, DailyTaskStatus
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.models.spike_suppression import SpikeSuppression
from app.models.transaction import Transaction, TransactionDirection
from app.models.user import User, CommuteMethod, EmploymentStatus, VehicleType
from app.models.user_locale import UserLocale

__all__ = [
    "User",
    "EmploymentStatus",
    "CommuteMethod",
    "VehicleType",
    "UserLocale",
    "Transaction",
    "TransactionDirection",
    "Category",
    "CategoryOverride",
    "CategoryWeight",
    "DailyTask",
    "DailyTaskStatus",
    "DailyTaskCompletionType",
    "Budget",
    "BudgetPeriodType",
    "BudgetPeriodRecord",
    "BudgetPeriodStatus",
    "BudgetLimitChangeLog",
    "Notification",
    "PushSubscription",
    "SpikeSuppression",
    "CoachingSuggestion",
    "CoachingSuggestionStatus",
]
