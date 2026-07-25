"""CategoryOverride model for tracking user category suggestion overrides.

When a user overrides a suggested category, this record is stored so future
suggestions prioritize the user's preferred category for the same note/amount pattern.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CategoryOverride(Base):
    """Tracks when a user overrides a suggested category.

    Stores the pattern (note or amount) and the category the user chose,
    so future suggestions can prioritize user preferences.
    """

    __tablename__ = "category_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The note pattern that triggered the override (nullable if override was amount-based)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The amount pattern that triggered the override (nullable if override was note-based)
    amount_smallest_unit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The category the user chose (the override)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    category: Mapped["Category"] = relationship("Category")

    def __repr__(self) -> str:
        return (
            f"<CategoryOverride(id={self.id}, user_id={self.user_id}, "
            f"note='{self.note}', amount={self.amount_smallest_unit})>"
        )
