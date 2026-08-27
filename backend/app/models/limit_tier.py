import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LimitTierKey(str, enum.Enum):
    """FR-16b: which bracket a sender's remittance limits are drawn from.

    Assumption: the tier is derived from KYC status (see
    app.services.limits.tier_for_user) rather than stored on the user -
    APPROVED maps to VERIFIED, everything else maps to UNVERIFIED. In
    practice UNVERIFIED is never reached through the quote endpoint since
    require_approved_kyc (FR-09) already blocks unapproved senders before
    the limit check runs; the tier still exists so an admin can configure
    it, matching the brief's example table.
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"


def _uuid() -> str:
    return str(uuid.uuid4())


class LimitTier(Base):
    __tablename__ = "limit_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tier_key: Mapped[LimitTierKey] = mapped_column(Enum(LimitTierKey), unique=True, nullable=False)
    daily_limit_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monthly_limit_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
