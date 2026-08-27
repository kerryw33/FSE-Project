from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class FeeConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixed_fee_zar: Decimal
    percentage_fee: Decimal
    fx_margin_percentage: Decimal
    cash_out_fee_percentage: Decimal


class FeeConfigUpdate(BaseModel):
    fixed_fee_zar: Decimal | None = Field(default=None, ge=0)
    percentage_fee: Decimal | None = Field(default=None, ge=0, le=1)
    fx_margin_percentage: Decimal | None = Field(default=None, ge=0, le=1)
    cash_out_fee_percentage: Decimal | None = Field(default=None, ge=0, le=1)


class LimitTierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tier_key: str
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal


class LimitTierUpdate(BaseModel):
    daily_limit_zar: Decimal | None = Field(default=None, ge=0)
    monthly_limit_zar: Decimal | None = Field(default=None, ge=0)
