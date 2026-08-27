from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().kyc_encryption_key
    if not key:
        raise RuntimeError(
            "KYC_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` and set it in the environment '
            "(NFR-04: keep it out of the database that stores encrypted values)."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedString(TypeDecorator):
    """Transparently encrypts a string column at rest (NFR-08a).

    Used for sensitive KYC fields such as the identification number so the
    plaintext value never touches the database file/backups.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return None
