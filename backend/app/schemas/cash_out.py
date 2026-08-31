from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.cash_out import CashOutStatus


class CashOutRequestCreate(BaseModel):
    rlusd_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=6)
    fiat_currency: str = Field(min_length=3, max_length=10)


class CashOutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    rlusd_amount: Decimal
    fiat_currency: str
    exchange_rate: Decimal
    cash_out_fee_percentage: Decimal
    fee_amount_rlusd: Decimal
    fiat_payout_amount: Decimal
    status: CashOutStatus
    created_at: datetime
    actioned_at: datetime | None
    completed_at: datetime | None
