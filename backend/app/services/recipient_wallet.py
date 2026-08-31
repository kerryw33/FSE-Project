from sqlalchemy.orm import Session as DBSession

from app.models.wallet import RecipientWallet
from app.services.xrpl_provisioning import establish_trustline, generate_and_fund_wallet


def get_or_create_wallet_row(db: DBSession, user_id: str) -> RecipientWallet:
    """FR-12b: the internal ledger row is created immediately when a
    beneficiary links to this user - fast, no network calls. The real
    XRPL account is provisioned lazily; see ensure_xrpl_account.
    """
    wallet = db.query(RecipientWallet).filter(RecipientWallet.user_id == user_id).first()
    if wallet is None:
        wallet = RecipientWallet(user_id=user_id)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


def ensure_xrpl_account(db: DBSession, wallet_row: RecipientWallet) -> RecipientWallet:
    """FR-27/FR-29: lazily generate, fund, and establish the TrustLine for
    this recipient's own custodial XRPL Testnet account, the first time
    it's actually needed (the first real settlement).

    XRP funding and the TrustLine itself are free/unlimited via the
    faucet - only RLUSD/UCTUSD token liquidity is scarce (see project
    memory "UCTUSD token details") - so this is safe to run for every
    recipient rather than gating it behind anything.
    """
    if wallet_row.xrpl_address is not None:
        return wallet_row

    funded_wallet = generate_and_fund_wallet()
    establish_trustline(funded_wallet)

    wallet_row.xrpl_address = funded_wallet.classic_address
    wallet_row.secret = funded_wallet.seed
    wallet_row.trustline_established = True
    db.add(wallet_row)
    db.commit()
    db.refresh(wallet_row)
    return wallet_row
