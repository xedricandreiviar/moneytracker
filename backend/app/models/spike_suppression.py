"""SpikeSuppression model for one-alert-per-category-per-week enforcement."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SpikeSuppression(Base):
    """Tracks which category/week combinations have already triggered a spike alert.

    Ensures at most one spike alert per category per week.
    """

    __tablename__ = "spike_suppressions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category_id", "week_start",
            name="uq_spike_user_category_week"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    category: Mapped["Category"] = relationship("Category")

    def __repr__(self) -> str:
        return (
            f"<SpikeSuppression(user_id={self.user_id}, "
            f"category_id={self.category_id}, week={self.week_start})>"
        )
