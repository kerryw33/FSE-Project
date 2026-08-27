from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import to_decimal
from app.models.fee_config import FeeConfig

TWO_PLACES = Decimal("0.01")
SIX_PLACES = Decimal("0.000001")


def _round(value: Decimal, places: Decimal) -> Decimal:
    return value.quantize(places, rounding=ROUND_HALF_UP)


@dataclass
class QuoteBreakdown:
    exchange_rate: Decimal
    fx_margin_percentage: Decimal
    transaction_fee_zar: Decimal
    rlusd_amount: Decimal
    cash_out_fee_percentage: Decimal
    estimated_cash_out_fee: Decimal
    estimated_recipient_payout: Decimal


def build_quote(zar_amount: Decimal, base_rate: Decimal, fee_config: FeeConfig) -> QuoteBreakdown:
    """FR-14/FR-15: compute the full fee/FX breakdown for a ZAR send amount.

    - transaction fee = fixed fee + a percentage of the ZAR amount
    - the FX margin is applied on top of the base rate (the sender's
      conversion happens at a worse rate than midmarket - the margin is
      the platform's spread), giving the "exchange rate used" shown in the
      quote
    - RLUSD is 1:1 with USD, so the ZAR remaining after the transaction fee
      converts at the margin-adjusted rate
    - the cash-out fee and resulting payout shown here are an *estimate*
      (FR-14) - the real cash-out is recalculated at cash-out time (FR-31)
      since the rate may have moved by then
    """
    fixed_fee = to_decimal(fee_config.fixed_fee_zar)
    percentage_fee = to_decimal(fee_config.percentage_fee)
    fx_margin_percentage = to_decimal(fee_config.fx_margin_percentage)
    cash_out_fee_percentage = to_decimal(fee_config.cash_out_fee_percentage)

    transaction_fee_zar = _round(fixed_fee + zar_amount * percentage_fee, TWO_PLACES)
    effective_rate = base_rate * (Decimal("1") + fx_margin_percentage)
    net_zar_for_conversion = zar_amount - transaction_fee_zar
    rlusd_amount = _round(net_zar_for_conversion / effective_rate, SIX_PLACES)

    estimated_cash_out_fee = _round(rlusd_amount * cash_out_fee_percentage, SIX_PLACES)
    estimated_recipient_payout = _round(rlusd_amount - estimated_cash_out_fee, SIX_PLACES)

    return QuoteBreakdown(
        exchange_rate=effective_rate,
        fx_margin_percentage=fx_margin_percentage,
        transaction_fee_zar=transaction_fee_zar,
        rlusd_amount=rlusd_amount,
        cash_out_fee_percentage=cash_out_fee_percentage,
        estimated_cash_out_fee=estimated_cash_out_fee,
        estimated_recipient_payout=estimated_recipient_payout,
    )
