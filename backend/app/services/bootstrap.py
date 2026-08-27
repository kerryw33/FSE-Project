from decimal import Decimal

from sqlalchemy.orm import Session as DBSession

from app.models.fee_config import FeeConfig
from app.models.limit_tier import LimitTier, LimitTierKey

# Mirrors the example table in the project brief (section: Remittance Limits).
DEFAULT_TIER_LIMITS = {
    LimitTierKey.UNVERIFIED: (Decimal("0"), Decimal("0")),
    LimitTierKey.VERIFIED: (Decimal("3000"), Decimal("25000")),
}


def seed_defaults(db: DBSession) -> None:
    """Seed the singleton fee config (FR-15a) and the default limit tiers
    (FR-16b) if they don't exist yet. Safe to call on every startup."""
    if db.query(FeeConfig).first() is None:
        db.add(FeeConfig())

    for tier_key, (daily, monthly) in DEFAULT_TIER_LIMITS.items():
        if db.query(LimitTier).filter(LimitTier.tier_key == tier_key).first() is None:
            db.add(LimitTier(tier_key=tier_key, daily_limit_zar=daily, monthly_limit_zar=monthly))

    db.commit()
