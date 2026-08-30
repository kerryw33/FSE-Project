from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


def _fernet(key_field: str) -> Fernet:
    key = getattr(get_settings(), key_field)
    if not key:
        env_name = key_field.upper()
        raise RuntimeError(
            f"{env_name} is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` and set it in the environment '
            "(NFR-04: keep it out of the database that stores encrypted values)."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedString(TypeDecorator):
    """Transparently encrypts a string column at rest (NFR-08a/NFR-04).

    `key_field` names the Settings attribute holding the Fernet key to use -
    different secret categories (KYC PII vs. XRPL private keys) use
    distinct keys, so a leak of one doesn't automatically expose the other.
    """

    impl = String
    cache_ok = True

    def __init__(self, *args, key_field: str = "kyc_encryption_key", **kwargs):
        super().__init__(*args, **kwargs)
        self.key_field = key_field

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet(self.key_field).encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet(self.key_field).decrypt(value.encode()).decode()
        except InvalidToken:
            return None
