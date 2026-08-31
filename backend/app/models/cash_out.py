import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CashOutStatus(str, enum.Enum):
    """FR-32: exactly the four states named in the brief."""

    REQUESTED = "requested"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"


def _uuid() -> str:
    return str(uuid.uuid4())


class CashOutRequest(Base):
    """FR-30/FR-31/FR-32: a recipient's request to convert RLUSD/UCTUSD
    back to fiat.

    The RLUSD amount is debited from the recipient's internal ledger
    balance immediately on request (see app.api.routes.cash_out) to
    prevent overdrawing via concurrent requests, and refunded if the
    request is later marked failed.
    """

    __tablename__ = "cash_out_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    rlusd_amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    fiat_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cash_out_fee_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    fee_amount_rlusd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    fiat_payout_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    status: Mapped[CashOutStatus] = mapped_column(
        Enum(CashOutStatus), default=CashOutStatus.REQUESTED, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actioned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
