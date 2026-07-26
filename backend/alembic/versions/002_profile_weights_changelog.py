"""Add profile fields to users, create category_weights and budget_limit_change_logs tables.

Revision ID: 002_profile_weights
Revises: 001_initial
Create Date: 2024-01-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_profile_weights"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add profile columns to users, create category_weights and budget_limit_change_logs."""

    # Add lifestyle profile columns to users table
    op.add_column(
        "users",
        sa.Column(
            "employment_status",
            sa.Enum("student", "working", "both", name="employmentstatus"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "commute_method",
            sa.Enum(
                "public_transit", "own_vehicle", "walking_biking", "none_remote",
                name="commutemethod",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "vehicle_type",
            sa.Enum("motorcycle", "car", name="vehicletype"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "profile_completed",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )

    # Create category_weights table
    op.create_table(
        "category_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_name", sa.String(100), nullable=False),
        sa.Column("weight_percentage", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("is_manual_override", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "category_name", name="uq_category_weight_user_category"
        ),
    )
    op.create_index("ix_category_weights_user_id", "category_weights", ["user_id"])

    # Create budget_limit_change_logs table
    op.create_table(
        "budget_limit_change_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=False),
        sa.Column("old_limit_smallest_unit", sa.Integer(), nullable=False),
        sa.Column("new_limit_smallest_unit", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("source_transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_budget_limit_change_logs_budget_id",
        "budget_limit_change_logs",
        ["budget_id"],
    )


def downgrade() -> None:
    """Remove profile columns and drop new tables."""

    # Drop budget_limit_change_logs table
    op.drop_table("budget_limit_change_logs")

    # Drop category_weights table
    op.drop_table("category_weights")

    # Remove profile columns from users
    op.drop_column("users", "profile_completed")
    op.drop_column("users", "vehicle_type")
    op.drop_column("users", "commute_method")
    op.drop_column("users", "employment_status")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS employmentstatus")
    op.execute("DROP TYPE IF EXISTS commutemethod")
    op.execute("DROP TYPE IF EXISTS vehicletype")
