from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.remittance import RemittanceStatus


class RemittanceQuoteRequest(BaseModel):
    beneficiary_id: str
    zar_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class RemittanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender_id: str
    beneficiary_id: str
    zar_amount: Decimal
    exchange_rate: Decimal
    fx_margin_percentage: Decimal
    transaction_fee_zar: Decimal
    rlusd_amount: Decimal
    cash_out_fee_percentage: Decimal
    estimated_cash_out_fee: Decimal
    estimated_recipient_payout: Decimal
    status: RemittanceStatus
    created_at: datetime
