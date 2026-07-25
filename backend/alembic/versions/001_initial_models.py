"""Initial models for Daily Money Tracker.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables."""

    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_last_updated_utc", sa.DateTime(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )

    # User locales table
    op.create_table(
        "user_locales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("currency_symbol", sa.String(5), nullable=False),
        sa.Column("decimal_precision", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("decimal_separator", sa.String(1), nullable=False, server_default="."),
        sa.Column(
            "thousands_separator", sa.String(1), nullable=False, server_default=","
        ),
        sa.Column(
            "date_format", sa.String(20), nullable=False, server_default="MM/DD/YYYY"
        ),
        sa.Column("week_start_day", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # Categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    # Transactions table
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_smallest_unit", sa.Integer(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("spent", "received", name="transactiondirection"),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("transaction_datetime_utc", sa.DateTime(), nullable=False),
        sa.Column("transaction_date_local", sa.Date(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index(
        "ix_transactions_user_date_local",
        "transactions",
        ["user_id", "transaction_date_local"],
    )
    op.create_index(
        "ix_transactions_user_category",
        "transactions",
        ["user_id", "category_id"],
    )

    # Daily tasks table
    op.create_table(
        "daily_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "missed", "grace_period", name="dailytaskstatus"),
            nullable=False,
        ),
        sa.Column(
            "completion_type",
            sa.Enum(
                "transaction_logged",
                "no_transactions",
                "grace_recovery",
                name="dailytaskcompletiontype",
            ),
            nullable=True,
        ),
        sa.Column("completed_at_utc", sa.DateTime(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_tasks_user_id", "daily_tasks", ["user_id"])
    op.create_index(
        "ix_daily_tasks_user_date", "daily_tasks", ["user_id", "task_date"], unique=True
    )

    # Budgets table
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column(
            "period_type",
            sa.Enum("weekly", "monthly", name="budgetperiodtype"),
            nullable=False,
        ),
        sa.Column("limit_smallest_unit", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])

    # Budget period records table
    op.create_table(
        "budget_period_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "spent_smallest_unit", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "exceeded", name="budgetperiodstatus"),
            nullable=False,
        ),
        sa.Column("report_generated_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_budget_period_records_budget_id", "budget_period_records", ["budget_id"]
    )
    op.create_index(
        "ix_budget_period_records_period",
        "budget_period_records",
        ["budget_id", "period_start"],
        unique=True,
    )

    # Notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read"],
    )

    # Spike suppressions table
    op.create_table(
        "spike_suppressions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "category_id", "week_start",
            name="uq_spike_user_category_week",
        ),
    )
    op.create_index(
        "ix_spike_suppressions_user_id", "spike_suppressions", ["user_id"]
    )

    # Coaching suggestions table
    op.create_table(
        "coaching_suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=False),
        sa.Column("deviation_percentage", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "dismissed", name="coachingsuggestionstatus"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("dismissed_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_coaching_suggestions_user_id", "coaching_suggestions", ["user_id"]
    )
    op.create_index(
        "ix_coaching_suggestions_budget_status",
        "coaching_suggestions",
        ["budget_id", "status"],
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("coaching_suggestions")
    op.drop_table("spike_suppressions")
    op.drop_table("notifications")
    op.drop_table("budget_period_records")
    op.drop_table("budgets")
    op.drop_table("daily_tasks")
    op.drop_table("transactions")
    op.drop_table("categories")
    op.drop_table("user_locales")
    op.drop_table("users")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS transactiondirection")
    op.execute("DROP TYPE IF EXISTS dailytaskstatus")
    op.execute("DROP TYPE IF EXISTS dailytaskcompletiontype")
    op.execute("DROP TYPE IF EXISTS budgetperiodtype")
    op.execute("DROP TYPE IF EXISTS budgetperiodstatus")
    op.execute("DROP TYPE IF EXISTS coachingsuggestionstatus")
