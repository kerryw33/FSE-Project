from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.core.money import to_decimal
from app.models.kyc import KYCStatus
from app.models.limit_tier import LimitTier, LimitTierKey
from app.models.remittance import Remittance
from app.models.user import User


def tier_for_user(user: User) -> LimitTierKey:
    """FR-16b assumption: the tier is derived from KYC status rather than
    stored separately - approved senders get VERIFIED, everyone else gets
    UNVERIFIED (see LimitTierKey docstring for why UNVERIFIED is effectively
    unreachable in practice)."""
    application = user.kyc_application
    if application is not None and application.status == KYCStatus.APPROVED:
        return LimitTierKey.VERIFIED
    return LimitTierKey.UNVERIFIED


def get_tier_limits(db: DBSession, tier_key: LimitTierKey) -> LimitTier:
    tier = db.query(LimitTier).filter(LimitTier.tier_key == tier_key).first()
    if tier is None:
        raise RuntimeError(f"Limit tier '{tier_key.value}' is not configured - seeding must have failed")
    return tier


def _sum_amount_since(db: DBSession, sender_id: str, since: datetime) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(Remittance.zar_amount), 0))
        .filter(Remittance.sender_id == sender_id, Remittance.created_at >= since)
        .scalar()
    )
    return to_decimal(total)


def usage_today(db: DBSession, sender_id: str) -> Decimal:
    """FR-16/FR-17: ZAR already committed today (UTC calendar day)."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return _sum_amount_since(db, sender_id, start_of_day)


def usage_this_month(db: DBSession, sender_id: str) -> Decimal:
    """FR-16/FR-17: ZAR already committed this calendar month (UTC)."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return _sum_amount_since(db, sender_id, start_of_month)
