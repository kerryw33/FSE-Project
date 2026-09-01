"""Benchmarks two things the HTTP load test (perf/locustfile.py) deliberately
doesn't cover, since mixing them into the concurrent-user run would measure
external network/faucet latency rather than the API's own performance:

- message-queue throughput: SettlementMessage enqueue rate (a DB write plus
  a Redis Stream XADD)
- RLUSD/UCTUSD transaction processing time: real XRPL Testnet Payment per
  settled remittance

Run after scripts/setup_platform_wallet.py. Uses a small number of real
transactions by default (5) to keep runtime and faucet/network load
reasonable - this specifically measures live network latency, not
something that benefits from a bigger sample.

    python -m scripts.benchmark_settlement [count]
"""

import sys
import time
from decimal import Decimal

sys.path.insert(0, ".")

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.beneficiary import Beneficiary  # noqa: E402
from app.models.fee_config import FeeConfig  # noqa: E402
from app.models.remittance import Remittance, RemittanceStatus  # noqa: E402
from app.models.settlement import SettlementMessage  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.beneficiary_linking import try_link_beneficiary  # noqa: E402
from app.services.redis_client import get_redis_client  # noqa: E402
from app.services.exchange_rate import get_usd_zar_rate  # noqa: E402
from app.services.platform_wallet import get_platform_wallet_row  # noqa: E402
from app.services.quote import build_quote  # noqa: E402
from app.services.settlement import STREAM_NAME, enqueue_settlement, process_pending_settlements  # noqa: E402


def _get_or_create_user(db, email, mobile, full_name):
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(full_name=full_name, email=email, mobile_number=mobile, password_hash=hash_password("BenchmarkPass123"))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _get_or_create_linked_beneficiary(db, sender, recipient):
    beneficiary = (
        db.query(Beneficiary)
        .filter(Beneficiary.sender_id == sender.id, Beneficiary.linked_user_id == recipient.id)
        .first()
    )
    if beneficiary is None:
        beneficiary = Beneficiary(
            sender_id=sender.id,
            full_name=recipient.full_name,
            email_address=recipient.email,
            country="South Africa",
            payout_currency="USD",
            relationship_to_sender="Friend",
        )
        db.add(beneficiary)
        db.commit()
        db.refresh(beneficiary)
        try_link_beneficiary(db, beneficiary)
        db.commit()
    return beneficiary


def _make_confirmed_remittance(db, sender, beneficiary, fee_config, base_rate) -> Remittance:
    quote = build_quote(Decimal("50.00"), base_rate, fee_config)
    remittance = Remittance(
        sender_id=sender.id,
        beneficiary_id=beneficiary.id,
        zar_amount=Decimal("50.00"),
        exchange_rate=quote.exchange_rate,
        fx_margin_percentage=quote.fx_margin_percentage,
        transaction_fee_zar=quote.transaction_fee_zar,
        rlusd_amount=quote.rlusd_amount,
        cash_out_fee_percentage=quote.cash_out_fee_percentage,
        estimated_cash_out_fee=quote.estimated_cash_out_fee,
        estimated_recipient_payout=quote.estimated_recipient_payout,
        status=RemittanceStatus.CASH_IN_CONFIRMED,
    )
    db.add(remittance)
    db.commit()
    db.refresh(remittance)
    return remittance


def benchmark_queue_throughput(db, sender, beneficiary, fee_config, base_rate, n=200):
    remittances = [_make_confirmed_remittance(db, sender, beneficiary, fee_config, base_rate) for _ in range(n)]

    start = time.perf_counter()
    messages = [enqueue_settlement(db, remittance) for remittance in remittances]
    elapsed = time.perf_counter() - start

    print(f"Message-queue enqueue: {n} messages in {elapsed:.3f}s ({n / elapsed:.1f} msg/s)")

    # Cleanup - these existed only to time the enqueue path, not to be
    # settled. Must remove both the DB rows AND the Redis stream entries
    # enqueue_settlement published: deleting the DB row does not undo the
    # XADD, and a dangling entry sits ahead of real work in the stream's
    # FIFO order, forcing every future read to burn through it first (this
    # caused a real bug once - a backlog of these starved a genuine
    # pending settlement out of a single bounded read).
    redis_client = get_redis_client()
    message_ids = {message.id for message in messages}
    entries_to_remove = [
        entry_id
        for entry_id, fields in redis_client.xrevrange(STREAM_NAME, count=n)
        if fields.get("settlement_message_id") in message_ids
    ]
    if entries_to_remove:
        redis_client.xdel(STREAM_NAME, *entries_to_remove)

    for remittance in remittances:
        db.query(SettlementMessage).filter(SettlementMessage.remittance_id == remittance.id).delete()
        db.delete(remittance)
    db.commit()


def benchmark_settlement_processing(db, sender, beneficiary, fee_config, base_rate, n=5):
    remittances = [_make_confirmed_remittance(db, sender, beneficiary, fee_config, base_rate) for _ in range(n)]
    for remittance in remittances:
        enqueue_settlement(db, remittance)

    start = time.perf_counter()
    results = process_pending_settlements(db, batch_size=n)
    elapsed = time.perf_counter() - start

    completed = [r for r in results if r.status.value == "completed"]
    failed = [r for r in results if r.status.value == "failed"]

    print(f"Settlement processing: {len(results)} real XRPL transactions in {elapsed:.3f}s")
    print(f"  avg per transaction: {elapsed / len(results):.3f}s")
    print(f"  completed: {len(completed)}, failed: {len(failed)}")
    for r in failed:
        print(f"    failed: {r.remittance_id} - {r.failure_reason}")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    db = SessionLocal()
    try:
        if get_platform_wallet_row(db) is None:
            print("No platform wallet set up - run `python -m scripts.setup_platform_wallet` first.")
            return

        sender = _get_or_create_user(db, "benchmark-sender@example.com", "+27821000001", "Benchmark Sender")
        recipient = _get_or_create_user(db, "benchmark-recipient@example.com", "+27821000002", "Benchmark Recipient")
        beneficiary = _get_or_create_linked_beneficiary(db, sender, recipient)

        fee_config = db.query(FeeConfig).first()
        base_rate = get_usd_zar_rate()

        print("== Message queue throughput (200 enqueue operations) ==")
        benchmark_queue_throughput(db, sender, beneficiary, fee_config, base_rate, n=200)

        print()
        print(f"== RLUSD settlement processing time ({n} real XRPL Testnet transactions) ==")
        benchmark_settlement_processing(db, sender, beneficiary, fee_config, base_rate, n=n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
