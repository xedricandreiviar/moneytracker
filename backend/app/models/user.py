"""User model with optimistic locking for streak updates."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmploymentStatus(str, enum.Enum):
    """User employment/income status."""

    student = "student"
    working = "working"
    both = "both"


class CommuteMethod(str, enum.Enum):
    """User commute method."""

    public_transit = "public_transit"
    own_vehicle = "own_vehicle"
    walking_biking = "walking_biking"
    none_remote = "none_remote"


class VehicleType(str, enum.Enum):
    """User vehicle type (applicable when commute_method is own_vehicle)."""

    motorcycle = "motorcycle"
    car = "car"


class User(Base):
    """User account with streak tracking, lifestyle profile, and optimistic locking."""

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

    # Lifestyle profile fields (Requirement 15)
    employment_status: Mapped[EmploymentStatus | None] = mapped_column(
        Enum(EmploymentStatus), nullable=True
    )
    commute_method: Mapped[CommuteMethod | None] = mapped_column(
        Enum(CommuteMethod), nullable=True
    )
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        Enum(VehicleType), nullable=True
    )
    profile_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

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
    category_weights: Mapped[list["CategoryWeight"]] = relationship(
        "CategoryWeight", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, streak={self.current_streak})>"
