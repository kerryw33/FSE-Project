import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RemittanceStatus(str, enum.Enum):
    """Settlement/queue states (FR-21 onward: SETTLEMENT_QUEUED, SETTLED,
    FAILED) are added when Queue & Settlement is implemented - this row is
    designed to be extended in place rather than replaced."""

    QUOTED = "quoted"
    CASH_IN_PENDING = "cash_in_pending"
    CASH_IN_CONFIRMED = "cash_in_confirmed"


class CashInMethod(str, enum.Enum):
    """FR-18: one supported simulated ZAR payment method per remittance."""

    AGENT_CASH = "agent_cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"


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

    FR-18/FR-19/FR-20: the sender initiates a simulated cash-in (locking in
    a method and moving to CASH_IN_PENDING), and an admin confirms receipt
    (moving to CASH_IN_CONFIRMED). No settlement mechanism exists yet
    (that's FR-21 onward), so FR-20's "must not begin settlement before
    cash-in is confirmed" is trivially satisfied for now - CASH_IN_CONFIRMED
    is simply the state the future settlement worker will watch for.
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

    cash_in_method: Mapped[CashInMethod | None] = mapped_column(Enum(CashInMethod), nullable=True)
    cash_in_initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cash_in_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cash_in_confirmed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    beneficiary: Mapped["Beneficiary"] = relationship("Beneficiary")
