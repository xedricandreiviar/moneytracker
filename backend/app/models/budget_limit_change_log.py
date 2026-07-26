"""BudgetLimitChangeLog model for tracking dynamic budget limit changes."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BudgetLimitChangeLog(Base):
    """Logs changes to budget limits triggered by income transactions.

    Each entry records the old and new limit values, the reason for the change,
    and the source transaction that triggered the recalculation.
    """

    __tablename__ = "budget_limit_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_limit_smallest_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    new_limit_smallest_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    source_transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    budget: Mapped["Budget"] = relationship("Budget")
    source_transaction: Mapped["Transaction | None"] = relationship("Transaction")

    def __repr__(self) -> str:
        return (
            f"<BudgetLimitChangeLog(id={self.id}, budget_id={self.budget_id}, "
            f"old={self.old_limit_smallest_unit}, new={self.new_limit_smallest_unit})>"
        )
