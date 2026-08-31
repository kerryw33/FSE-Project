from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import to_decimal
from app.models.fee_config import FeeConfig
from app.services.exchange_rate import get_usd_zar_rate

TWO_PLACES = Decimal("0.01")
SIX_PLACES = Decimal("0.000001")

SUPPORTED_FIAT_CURRENCIES = {"USD", "ZAR"}


@dataclass
class CashOutQuote:
    exchange_rate: Decimal
    fee_percentage: Decimal
    fee_amount_rlusd: Decimal
    fiat_payout_amount: Decimal


def build_cash_out_quote(rlusd_amount: Decimal, fiat_currency: str, fee_config: FeeConfig) -> CashOutQuote:
    """FR-31: the fiat payout using the applicable exchange rate, less the
    configured cash-out fee. RLUSD/UCTUSD is 1:1 with USD, so a USD
    cash-out is a straight passthrough after the fee; a ZAR cash-out
    additionally applies the configured USD/ZAR rate (no FX margin here -
    FR-31 only names "the applicable exchange rate" and the cash-out fee,
    unlike the remittance quote which explicitly adds a margin).
    """
    if fiat_currency not in SUPPORTED_FIAT_CURRENCIES:
        raise ValueError(f"Unsupported fiat currency: {fiat_currency}")

    fee_percentage = to_decimal(fee_config.cash_out_fee_percentage)
    fee_amount_rlusd = (rlusd_amount * fee_percentage).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
    net_rlusd = rlusd_amount - fee_amount_rlusd

    if fiat_currency == "USD":
        exchange_rate = Decimal("1")
    else:
        exchange_rate = get_usd_zar_rate()

    fiat_payout_amount = (net_rlusd * exchange_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    return CashOutQuote(
        exchange_rate=exchange_rate,
        fee_percentage=fee_percentage,
        fee_amount_rlusd=fee_amount_rlusd,
        fiat_payout_amount=fiat_payout_amount,
    )
