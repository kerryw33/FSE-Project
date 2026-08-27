import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class FeeConfig(Base):
    """FR-15/FR-15a: the active set of fee parameters, admin-editable.

    Modelled as a single row rather than a history table - there is no
    requirement to version fee changes, just to have them configurable.
    Percentage fields are fractions (0.0100 = 1%), not whole percentages.
    """

    __tablename__ = "fee_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fixed_fee_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("25.00"))
    percentage_fee: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0100"))
    fx_margin_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0200"))
    cash_out_fee_percentage: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.0150")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
