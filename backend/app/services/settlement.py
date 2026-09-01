from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session as DBSession

from app.core.money import to_decimal
from app.models.remittance import Remittance, RemittanceStatus
from app.models.settlement import SettlementMessage, SettlementMessageStatus
from app.services.platform_wallet import get_platform_wallet_row
from app.services.recipient_wallet import ensure_xrpl_account, get_or_create_wallet_row
from app.services.redis_client import get_redis_client
from app.services.xrpl_provisioning import submit_issued_currency_payment

# FR-21/22: the settlement queue, as a Redis Stream (basics.pdf recommends
# RabbitMQ/Redis Streams over a DB-polling table). Entries just carry a
# SettlementMessage id - the durable record of status/outcome/tx-hash stays
# in that DB row (FR-23/NFR-09 need it queryable regardless of queue tech),
# so the stream is purely the transport that wakes a consumer up.
STREAM_NAME = "settlement_messages"
GROUP_NAME = "settlement_workers"
CONSUMER_NAME = "worker-1"  # FR-22 names "a settlement worker", singular


def _ensure_consumer_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _push_to_stream(client: redis.Redis, settlement_message_id: str) -> None:
    _ensure_consumer_group(client)
    client.xadd(STREAM_NAME, {"settlement_message_id": settlement_message_id})


def enqueue_settlement(db: DBSession, remittance: Remittance) -> SettlementMessage:
    """FR-21: place a settlement message on the queue once cash-in is
    confirmed. Idempotent per remittance - the unique constraint on
    remittance_id means calling this twice for the same remittance just
    returns the existing message rather than creating a second one (and
    never re-publishes to the stream either).
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

    _push_to_stream(get_redis_client(), message.id)
    return message


def retry_settlement_message(db: DBSession, message: SettlementMessage) -> SettlementMessage:
    """Not mandated by any FR, but FR-24's failure handling is only useful
    in practice if a failed settlement can be tried again. Resets the DB
    row and re-publishes to the stream - a message that failed doesn't
    get automatically redelivered by Redis once acked, so without this it
    would sit FAILED forever with no consumer ever seeing it again.
    """
    message.status = SettlementMessageStatus.PENDING
    message.failure_reason = None
    db.add(message)

    message.remittance.status = RemittanceStatus.SETTLEMENT_QUEUED
    message.remittance.settlement_failure_reason = None
    db.add(message.remittance)

    db.commit()
    db.refresh(message)

    _push_to_stream(get_redis_client(), message.id)
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


def process_pending_settlements(db: DBSession, batch_size: int = 50, block_ms: int = 200) -> list[SettlementMessage]:
    """FR-22: the settlement worker's main loop body - fully drain whatever
    is waiting on the Redis Stream, processing and acking each entry. This
    is what both the standalone worker script and the admin-triggered
    manual run call.

    Loops rather than reading a single bounded batch: `count` on
    XREADGROUP caps one call, so a single read would leave anything past
    the cap stuck behind it until the next call - including a backlog of
    entries whose SettlementMessage row no longer exists (skipped as a
    no-op below, but they still occupy stream position and must be acked
    past before real work behind them is ever reached). Looping until a
    batch comes back smaller than requested means one call always
    processes everything currently available, not just the first
    `batch_size` items in FIFO order.

    Acks immediately after processing regardless of outcome - retries are
    handled explicitly via retry_settlement_message(), not via Redis's own
    pending-entry redelivery, so a message is never left claimed-but-
    unacked for something else to pick up later.
    """
    client = get_redis_client()
    _ensure_consumer_group(client)

    results = []
    while True:
        response = client.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=batch_size, block=block_ms)
        if not response:
            break

        entries_seen = 0
        for _stream_name, entries in response:
            entries_seen += len(entries)
            for entry_id, fields in entries:
                settlement_message_id = fields.get("settlement_message_id")
                message = db.query(SettlementMessage).filter(SettlementMessage.id == settlement_message_id).first()
                if message is not None:
                    results.append(process_settlement_message(db, message))
                client.xack(STREAM_NAME, GROUP_NAME, entry_id)

        if entries_seen < batch_size:
            break  # caught up to the live edge of the stream

    return results
