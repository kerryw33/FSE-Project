from sqlalchemy.orm import Session as DBSession
from xrpl.account import get_balance

from app.models.platform_wallet import PlatformWallet
from app.services.xrpl_client import get_xrpl_client
from app.services.xrpl_provisioning import establish_trustline as _establish_trustline
from app.services.xrpl_provisioning import generate_and_fund_wallet


def get_platform_wallet_row(db: DBSession) -> PlatformWallet | None:
    """Only one row should ever exist - it's the single treasury account
    that funds every recipient's custodial wallet (see project memory
    "pooled wallet architecture")."""
    return db.query(PlatformWallet).first()


def get_or_create_platform_wallet(db: DBSession) -> PlatformWallet:
    """Generate and fund a new XRPL Testnet account for the platform if one
    doesn't already exist, and persist it with its secret encrypted
    (NFR-04/05). Idempotent - safe to call repeatedly.
    """
    existing = get_platform_wallet_row(db)
    if existing is not None:
        return existing

    funded_wallet = generate_and_fund_wallet()

    row = PlatformWallet(
        classic_address=funded_wallet.classic_address,
        secret=funded_wallet.seed,
        network="testnet",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def establish_trustline(db: DBSession, wallet_row: PlatformWallet) -> str:
    """FR-29: submit the TrustSet transaction to the configured issuer so
    this wallet can hold RLUSD/UCTUSD. Returns the transaction hash.

    The secret is decrypted only for the moment of signing and is never
    logged or returned to any caller (NFR-05).
    """
    from xrpl.wallet import Wallet

    wallet = Wallet.from_seed(wallet_row.secret)
    tx_hash = _establish_trustline(wallet)

    wallet_row.trustline_established = True
    db.add(wallet_row)
    db.commit()
    db.refresh(wallet_row)
    return tx_hash


def get_xrp_balance(wallet_row: PlatformWallet) -> str:
    client = get_xrpl_client()
    return get_balance(wallet_row.classic_address, client)
