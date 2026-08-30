from sqlalchemy.orm import Session as DBSession
from xrpl.account import get_balance
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.transactions import TrustSet
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

from app.config import get_settings
from app.models.platform_wallet import PlatformWallet
from app.services.xrpl_client import get_xrpl_client


def get_platform_wallet_row(db: DBSession) -> PlatformWallet | None:
    """Pooled-wallet model (see project memory "pooled wallet
    architecture"): at most one row should ever exist."""
    return db.query(PlatformWallet).first()


def get_or_create_platform_wallet(db: DBSession) -> PlatformWallet:
    """Generate and fund a new XRPL Testnet account for the platform if one
    doesn't already exist, and persist it with its secret encrypted
    (NFR-04/05). Idempotent - safe to call repeatedly.
    """
    existing = get_platform_wallet_row(db)
    if existing is not None:
        return existing

    client = get_xrpl_client()
    funded_wallet = generate_faucet_wallet(client, debug=False)

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
    settings = get_settings()
    client = get_xrpl_client()
    wallet = Wallet.from_seed(wallet_row.secret)

    trust_set = TrustSet(
        account=wallet.classic_address,
        limit_amount=IssuedCurrencyAmount(
            currency=settings.xrpl_currency_code,
            issuer=settings.xrpl_issuer_address,
            value=settings.xrpl_trustline_limit,
        ),
    )
    response = submit_and_wait(trust_set, client, wallet)
    tx_result = response.result["meta"]["TransactionResult"]
    if tx_result != "tesSUCCESS":
        raise RuntimeError(f"TrustSet failed: {tx_result}")

    wallet_row.trustline_established = True
    db.add(wallet_row)
    db.commit()
    db.refresh(wallet_row)
    return response.result["hash"]


def get_xrp_balance(wallet_row: PlatformWallet) -> str:
    client = get_xrpl_client()
    return get_balance(wallet_row.classic_address, client)
