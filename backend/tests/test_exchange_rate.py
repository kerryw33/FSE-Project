from decimal import Decimal

from app.services import exchange_rate


def test_falls_back_to_configured_rate_when_live_fetch_fails(monkeypatch):
    """This is also exactly what the autouse fixture in conftest.py relies
    on for every other test in the suite."""
    monkeypatch.setattr(exchange_rate, "_fetch_live_rate", lambda: None)
    exchange_rate._cache["rate"] = None
    exchange_rate._cache["fetched_at"] = 0.0

    rate = exchange_rate.get_usd_zar_rate()
    assert rate == Decimal("18.50")


def test_uses_live_rate_when_available(monkeypatch):
    monkeypatch.setattr(exchange_rate, "_fetch_live_rate", lambda: Decimal("16.42"))
    exchange_rate._cache["rate"] = None
    exchange_rate._cache["fetched_at"] = 0.0

    rate = exchange_rate.get_usd_zar_rate()
    assert rate == Decimal("16.42")


def test_caches_rate_and_does_not_refetch_within_ttl(monkeypatch):
    calls = {"count": 0}

    def fake_fetch():
        calls["count"] += 1
        return Decimal("17.00")

    monkeypatch.setattr(exchange_rate, "_fetch_live_rate", fake_fetch)
    exchange_rate._cache["rate"] = None
    exchange_rate._cache["fetched_at"] = 0.0

    first = exchange_rate.get_usd_zar_rate()
    second = exchange_rate.get_usd_zar_rate()

    assert first == second == Decimal("17.00")
    assert calls["count"] == 1  # second call served from cache, not refetched


def test_refetches_after_cache_expires(monkeypatch):
    import time

    calls = {"count": 0}

    def fake_fetch():
        calls["count"] += 1
        return Decimal("17.00")

    monkeypatch.setattr(exchange_rate, "_fetch_live_rate", fake_fetch)
    # Simulate a cached rate from well past the default 300s TTL, rather
    # than fiddling with Settings' lru_cache - simpler and just as valid.
    exchange_rate._cache["rate"] = Decimal("16.00")
    exchange_rate._cache["fetched_at"] = time.monotonic() - 301

    rate = exchange_rate.get_usd_zar_rate()

    assert rate == Decimal("17.00")
    assert calls["count"] == 1
