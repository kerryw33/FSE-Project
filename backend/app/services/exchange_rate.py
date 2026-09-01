import time
from decimal import Decimal

import httpx

from app.config import get_settings

_cache: dict = {"rate": None, "fetched_at": 0.0}


def _fetch_live_rate() -> Decimal | None:
    """One HTTP call to the configured public exchange-rate API. Isolated
    into its own function so tests can monkeypatch just this - the network
    call, not the caching/fallback logic around it.

    Returns None on any failure (network error, timeout, non-2xx, missing
    ZAR field) rather than raising - a flaky third-party API should never
    be able to break quote creation, which falls back to the configured
    static rate instead (FR-13 permits "a public API, mock service, or
    configured rate table" - this combines the first and third).
    """
    settings = get_settings()
    try:
        response = httpx.get(settings.exchange_rate_api_url, timeout=settings.exchange_rate_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return Decimal(str(data["rates"]["ZAR"]))
    except Exception:
        return None


def get_usd_zar_rate() -> Decimal:
    """FR-13: the USD/ZAR exchange rate applicable right now.

    Fetched from a live public API and cached for
    `exchange_rate_cache_seconds` (default 5 minutes) - long enough that
    50 concurrent users creating quotes doesn't turn into 50 concurrent
    calls to a free third-party API, short enough that "applicable right
    now" stays meaningful. Falls back to the configured static rate
    (`USD_ZAR_RATE`) if the live fetch fails for any reason.
    """
    settings = get_settings()
    now = time.monotonic()

    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < settings.exchange_rate_cache_seconds:
        return _cache["rate"]

    rate = _fetch_live_rate()
    if rate is None:
        rate = Decimal(str(settings.usd_zar_rate))

    _cache["rate"] = rate
    _cache["fetched_at"] = now
    return rate
