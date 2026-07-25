"""Transaction model storing monetary amounts in smallest currency unit."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionDirection(str, enum.Enum):
    """Direction of money flow."""

    spent = "spent"
    received = "received"


class Transaction(Base):
    """Financial transaction with amount stored in smallest currency unit.

    E.g., 1050 with currency_code='USD' = $10.50;
          1050 with currency_code='JPY' = ¥1050.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount_smallest_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(
        Enum(TransactionDirection), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_datetime_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    # Local date for efficient date-based queries without timezone conversion
    transaction_date_local: Mapped[date] = mapped_column(Date, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="transactions"
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.id}, amount={self.amount_smallest_unit}, "
            f"currency={self.currency_code}, direction={self.direction.value})>"
        )
