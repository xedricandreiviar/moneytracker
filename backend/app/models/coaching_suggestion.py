"""CoachingSuggestion model for AI proactive budget coaching."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CoachingSuggestionStatus(str, enum.Enum):
    """Status of a coaching suggestion."""

    pending = "pending"
    accepted = "accepted"
    dismissed = "dismissed"


class CoachingSuggestion(Base):
    """AI-generated coaching suggestion based on budget deviation detection."""

    __tablename__ = "coaching_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    budget_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    deviation_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[CoachingSuggestionStatus] = mapped_column(
        Enum(CoachingSuggestionStatus),
        nullable=False,
        default=CoachingSuggestionStatus.pending,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    dismissed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    budget: Mapped["Budget"] = relationship("Budget")

    def __repr__(self) -> str:
        return (
            f"<CoachingSuggestion(id={self.id}, budget_id={self.budget_id}, "
            f"deviation={self.deviation_percentage}%, status={self.status.value})>"
        )
