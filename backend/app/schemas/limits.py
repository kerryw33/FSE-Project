from decimal import Decimal

from pydantic import BaseModel


class LimitStatusOut(BaseModel):
    tier: str
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal
    used_today_zar: Decimal
    used_this_month_zar: Decimal
    remaining_today_zar: Decimal
    remaining_this_month_zar: Decimal
