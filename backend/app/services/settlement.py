from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from app.core.money import to_decimal
from app.models.remittance import Remittance, RemittanceStatus
from app.models.settlement import SettlementMessage, SettlementMessageStatus
from app.services.platform_wallet import get_platform_wallet_row
from app.services.recipient_wallet import ensure_xrpl_account, get_or_create_wallet_row
from app.services.xrpl_provisioning import submit_issued_currency_payment


def enqueue_settlement(db: DBSession, remittance: Remittance) -> SettlementMessage:
    """FR-21: place a settlement message on the queue once cash-in is
    confirmed. Idempotent per remittance - the unique constraint on
    remittance_id means calling this twice for the same remittance just
    returns the existing message rather than creating a second one.
    """
    existing = db.query(SettlementMessage).filter(SettlementMessage.remittance_id == remittance.id).first()
    if existing is not None:
        return existing

    message = SettlementMessage(remittance_id=remittance.id)
    db.add(message)
    remittance.status = RemittanceStatus.SETTLEMENT_QUEUED
    db.add(remittance)
    db.commit()
    db.refresh(message)
    return message


def process_settlement_message(db: DBSession, message: SettlementMessage) -> SettlementMessage:
    """FR-22: consume one queued message and submit the corresponding
    RLUSD/UCTUSD Payment to the XRP Ledger Testnet, from the platform
    treasury wallet to the recipient's own custodial account.

    FR-24: on failure, the recipient's wallet balance is left untouched
    and the failure reason is recorded on both the message and the
    remittance.
    FR-25: a message already COMPLETED is a no-op rather than crediting
    the wallet again - covers a message somehow being processed twice
    (e.g. re-run after a crash before the caller saw the result).
    FR-26: on success, the recipient's cached ledger balance is credited.
    """
    if message.status == SettlementMessageStatus.COMPLETED:
        return message

    remittance = message.remittance
    beneficiary = remittance.beneficiary

    message.status = SettlementMessageStatus.PROCESSING
    message.attempts += 1
    db.add(message)
    db.commit()

    try:
        if beneficiary.linked_user_id is None:
            raise RuntimeError("Beneficiary is not linked to a registered recipient account")

        platform_wallet_row = get_platform_wallet_row(db)
        if platform_wallet_row is None:
            raise RuntimeError("Platform wallet is not set up")

        recipient_wallet_row = get_or_create_wallet_row(db, beneficiary.linked_user_id)
        recipient_wallet_row = ensure_xrpl_account(db, recipient_wallet_row)

        tx_hash = submit_issued_currency_payment(
            platform_wallet_row.secret, recipient_wallet_row.xrpl_address, remittance.rlusd_amount
        )

        recipient_wallet_row.balance = to_decimal(recipient_wallet_row.balance) + remittance.rlusd_amount
        db.add(recipient_wallet_row)

        remittance.status = RemittanceStatus.SETTLED
        remittance.xrpl_settlement_tx_hash = tx_hash
        remittance.settled_at = datetime.now(timezone.utc)
        db.add(remittance)

        message.status = SettlementMessageStatus.COMPLETED
        message.processed_at = datetime.now(timezone.utc)
        db.add(message)
        db.commit()
    except Exception as exc:
        db.rollback()

        message.status = SettlementMessageStatus.FAILED
        message.failure_reason = str(exc)
        message.processed_at = datetime.now(timezone.utc)
        db.add(message)

        remittance.status = RemittanceStatus.SETTLEMENT_FAILED
        remittance.settlement_failure_reason = str(exc)
        db.add(remittance)
        db.commit()

    db.refresh(message)
    return message


def process_pending_settlements(db: DBSession) -> list[SettlementMessage]:
    """FR-22: the settlement worker's main loop body - claim every PENDING
    message and process it. This is what both the standalone worker
    script and the admin-triggered manual run call.
    """
    pending = db.query(SettlementMessage).filter(SettlementMessage.status == SettlementMessageStatus.PENDING).all()
    return [process_settlement_message(db, message) for message in pending]
