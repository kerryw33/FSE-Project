from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.limits import LimitStatusOut
from app.services.limits import get_tier_limits, tier_for_user, usage_this_month, usage_today

router = APIRouter(prefix="/limits", tags=["limits"])


@router.get("/me", response_model=LimitStatusOut)
def get_my_limits(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """FR-16a: view current daily/monthly remittance limits and remaining
    available allowance."""
    tier_key = tier_for_user(current_user)
    tier = get_tier_limits(db, tier_key)

    daily_limit = Decimal(str(tier.daily_limit_zar))
    monthly_limit = Decimal(str(tier.monthly_limit_zar))
    used_today = usage_today(db, current_user.id)
    used_this_month = usage_this_month(db, current_user.id)

    return LimitStatusOut(
        tier=tier_key.value,
        daily_limit_zar=daily_limit,
        monthly_limit_zar=monthly_limit,
        used_today_zar=used_today,
        used_this_month_zar=used_this_month,
        remaining_today_zar=max(daily_limit - used_today, Decimal("0")),
        remaining_this_month_zar=max(monthly_limit - used_this_month, Decimal("0")),
    )
