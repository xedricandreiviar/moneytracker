"""DailyTask model for tracking daily financial logging habit."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyTaskStatus(str, enum.Enum):
    """Status of a daily task."""

    pending = "pending"
    completed = "completed"
    missed = "missed"
    grace_period = "grace_period"


class DailyTaskCompletionType(str, enum.Enum):
    """How the daily task was completed."""

    transaction_logged = "transaction_logged"
    no_transactions = "no_transactions"
    grace_recovery = "grace_recovery"


class DailyTask(Base):
    """Daily logging task that drives the streak mechanic."""

    __tablename__ = "daily_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "task_date", name="uq_daily_tasks_user_date"),
        Index("ix_daily_tasks_user_date", "user_id", "task_date", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[DailyTaskStatus] = mapped_column(
        Enum(DailyTaskStatus), nullable=False, default=DailyTaskStatus.pending
    )
    completion_type: Mapped[DailyTaskCompletionType | None] = mapped_column(
        Enum(DailyTaskCompletionType), nullable=True
    )
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="daily_tasks")

    def __repr__(self) -> str:
        return (
            f"<DailyTask(id={self.id}, user_id={self.user_id}, "
            f"date={self.task_date}, status={self.status.value})>"
        )
