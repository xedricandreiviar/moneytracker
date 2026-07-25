"""UserLocale model for country-driven currency and date formatting."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserLocale(Base):
    """Locale configuration tied to a user's selected country."""

    __tablename__ = "user_locales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    currency_symbol: Mapped[str] = mapped_column(String(5), nullable=False)
    decimal_precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    decimal_separator: Mapped[str] = mapped_column(
        String(1), nullable=False, default="."
    )
    thousands_separator: Mapped[str] = mapped_column(
        String(1), nullable=False, default=","
    )
    date_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MM/DD/YYYY"
    )
    week_start_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="locale")

    def __repr__(self) -> str:
        return (
            f"<UserLocale(user_id={self.user_id}, "
            f"country={self.country_code}, currency={self.currency_code})>"
        )
