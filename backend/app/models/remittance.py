import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RemittanceStatus(str, enum.Enum):
    """Only QUOTED exists in this slice. Cash-in confirmation and
    settlement states are added when FR-18 onward (Simulated Cash-In,
    Queue & Settlement) are implemented - this row is designed to be
    extended in place rather than replaced."""

    QUOTED = "quoted"


def _uuid() -> str:
    return str(uuid.uuid4())


class Remittance(Base):
    """FR-13/FR-14: a remittance transaction, created at quote time with
    the exchange rate and fee breakdown locked in.

    FR-16/FR-17: the sum of a sender's remittances created today/this
    calendar month is what the daily/monthly limit check is measured
    against (see app.services.limits) - creating a quote counts as
    "the transaction proceeding" for limit purposes, since no later
    confirmation step exists yet.
    """

    __tablename__ = "remittances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    beneficiary_id: Mapped[str] = mapped_column(String(36), ForeignKey("beneficiaries.id"), nullable=False)

    zar_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    fx_margin_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    transaction_fee_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    rlusd_amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cash_out_fee_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    estimated_cash_out_fee: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    estimated_recipient_payout: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)

    status: Mapped[RemittanceStatus] = mapped_column(
        Enum(RemittanceStatus), default=RemittanceStatus.QUOTED, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    sender: Mapped["User"] = relationship("User")
    beneficiary: Mapped["Beneficiary"] = relationship("Beneficiary")
