from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, loaded from environment / .env file.

    Kept as a single source of truth so later modules (remittance, wallet,
    XRPL settlement, message queue) can add their own settings here without
    scattering os.environ lookups across the codebase.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./fx_platform.db"
    session_expire_hours: int = 12
    kyc_encryption_key: str = ""

    # FR-13: fixed, configured USD/ZAR rate for this slice. Swappable later
    # for a public API without touching any caller of get_usd_zar_rate().
    usd_zar_rate: float = 18.50

    # XRPL Testnet Integration (FR-27-29). Issuer/currency are config, not
    # hardcoded, so switching between the fallback UCTUSD IOU and the real
    # RLUSD issuer later is a one-line change (per basics.pdf guidance).
    # Defaults below are UCTUSD, the course-provided fallback token.
    xrpl_json_rpc_url: str = "https://s.altnet.rippletest.net:51234/"
    xrpl_issuer_address: str = "rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5"
    xrpl_currency_code: str = "5543545553440000000000000000000000000000"
    xrpl_trustline_limit: str = "1000000"

    # Separate from kyc_encryption_key (NFR-04/05): a distinct key means a
    # leak of one secret category doesn't automatically expose the other.
    xrpl_key_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
