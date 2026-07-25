"""Budget and BudgetPeriodRecord models."""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BudgetPeriodType(str, enum.Enum):
    """Budget period duration type."""

    weekly = "weekly"
    monthly = "monthly"


class BudgetPeriodStatus(str, enum.Enum):
    """Status of a budget period record."""

    active = "active"
    completed = "completed"
    exceeded = "exceeded"


class Budget(Base):
    """User-defined spending budget for a category or overall."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL category_id means "overall" budget (all spending)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    period_type: Mapped[BudgetPeriodType] = mapped_column(
        Enum(BudgetPeriodType), nullable=False
    )
    limit_smallest_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="budgets")
    category: Mapped["Category | None"] = relationship("Category")
    period_records: Mapped[list["BudgetPeriodRecord"]] = relationship(
        "BudgetPeriodRecord", back_populates="budget", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return (
            f"<Budget(id={self.id}, period={self.period_type.value}, "
            f"limit={self.limit_smallest_unit}, active={self.is_active})>"
        )


class BudgetPeriodRecord(Base):
    """Tracks spending within a single budget period."""

    __tablename__ = "budget_period_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    spent_smallest_unit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    status: Mapped[BudgetPeriodStatus] = mapped_column(
        Enum(BudgetPeriodStatus), nullable=False, default=BudgetPeriodStatus.active
    )
    report_generated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships
    budget: Mapped["Budget"] = relationship("Budget", back_populates="period_records")

    def __repr__(self) -> str:
        return (
            f"<BudgetPeriodRecord(id={self.id}, budget_id={self.budget_id}, "
            f"period={self.period_start} to {self.period_end}, "
            f"spent={self.spent_smallest_unit})>"
        )
