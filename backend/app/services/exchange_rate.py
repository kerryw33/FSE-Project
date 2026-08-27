from decimal import Decimal

from app.config import get_settings


def get_usd_zar_rate() -> Decimal:
    """FR-13: the USD/ZAR exchange rate applicable right now.

    Sourced from a configured value for this slice (effectively a
    one-row rate table) rather than a live public API. Callers don't need
    to change when a real provider is wired in later - only this function
    does.
    """
    return Decimal(str(get_settings().usd_zar_rate))
