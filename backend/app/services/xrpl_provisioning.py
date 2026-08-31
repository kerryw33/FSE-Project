from decimal import Decimal

from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.transactions import Payment, TrustSet
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

from app.config import get_settings
from app.services.xrpl_client import get_xrpl_client


def generate_and_fund_wallet() -> Wallet:
    """Generate a new XRPL Testnet account and fund it with faucet XRP.

    Free and unlimited, unlike RLUSD/UCTUSD token liquidity (see project
    memory "UCTUSD token details") - safe to call for every recipient.
    """
    return generate_faucet_wallet(get_xrpl_client(), debug=False)


def establish_trustline(wallet: Wallet) -> str:
    """FR-29: TrustSet to the configured issuer/currency so `wallet` can
    hold RLUSD/UCTUSD. Returns the transaction hash."""
    settings = get_settings()
    client = get_xrpl_client()
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
    return response.result["hash"]


def submit_issued_currency_payment(from_seed: str, destination_address: str, amount: Decimal) -> str:
    """FR-22: submit a Payment transaction moving RLUSD/UCTUSD on-chain.

    Takes the sender's seed directly (rather than a Wallet object) so
    callers never need to construct a Wallet themselves - keeps the one
    place private keys get materialised into signing objects contained
    here (NFR-05).

    Returns the transaction hash. Raises RuntimeError if the ledger
    reports anything other than tesSUCCESS - e.g. tecUNFUNDED_PAYMENT if
    the sender lacks sufficient token balance, or tecNO_LINE if the
    destination hasn't trusted the issuer.
    """
    settings = get_settings()
    client = get_xrpl_client()
    wallet = Wallet.from_seed(from_seed)

    payment = Payment(
        account=wallet.classic_address,
        destination=destination_address,
        amount=IssuedCurrencyAmount(
            currency=settings.xrpl_currency_code,
            issuer=settings.xrpl_issuer_address,
            value=str(amount),
        ),
    )
    response = submit_and_wait(payment, client, wallet)
    tx_result = response.result["meta"]["TransactionResult"]
    if tx_result != "tesSUCCESS":
        raise RuntimeError(f"Payment failed: {tx_result}")
    return response.result["hash"]
