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


@lru_cache
def get_settings() -> Settings:
    return Settings()
