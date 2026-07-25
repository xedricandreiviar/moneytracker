"""User model with optimistic locking for streak updates."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """User account with streak tracking and optimistic locking."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_last_updated_utc: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    # Optimistic locking version column for streak updates
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    locale: Mapped["UserLocale"] = relationship(
        "UserLocale", back_populates="user", uselist=False, lazy="joined"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user", lazy="dynamic"
    )
    daily_tasks: Mapped[list["DailyTask"]] = relationship(
        "DailyTask", back_populates="user", lazy="dynamic"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        "Budget", back_populates="user", lazy="dynamic"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", lazy="dynamic"
    )
    categories: Mapped[list["Category"]] = relationship(
        "Category", back_populates="user", lazy="dynamic"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        "PushSubscription", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, streak={self.current_streak})>"
