"""CategoryWeight model for per-user budget category percentage allocations."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CategoryWeight(Base):
    """Percentage-based allocation for a budget category, per user.

    All CategoryWeight entries for a user must sum to exactly 100.00%.
    Weights are either derived from the Weight_Rules_Table based on the
    user's Lifestyle_Profile, or manually overridden by the user.
    """

    __tablename__ = "category_weights"
    __table_args__ = (
        UniqueConstraint("user_id", "category_name", name="uq_category_weight_user_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    weight_percentage: Mapped[Decimal] = mapped_column(
        Numeric(precision=4, scale=2), nullable=False
    )
    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="category_weights")

    def __repr__(self) -> str:
        return (
            f"<CategoryWeight(id={self.id}, user_id={self.user_id}, "
            f"category={self.category_name}, weight={self.weight_percentage}%, "
            f"manual={self.is_manual_override})>"
        )
