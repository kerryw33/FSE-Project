"""Consume pending settlement messages and submit the corresponding
RLUSD/UCTUSD transfers to the XRP Ledger Testnet (FR-22).

Run standalone, e.g. on a timer/cron:

    python -m scripts.run_settlement_worker

(Equivalently, POST /admin/settlement/run triggers the same function from
the API, for demonstrating the flow without a second long-lived process.)
"""

import sys

sys.path.insert(0, ".")

from app.database import SessionLocal  # noqa: E402
from app.services.settlement import process_pending_settlements  # noqa: E402


def main():
    db = SessionLocal()
    try:
        results = process_pending_settlements(db)
        if not results:
            print("No pending settlement messages.")
            return
        for message in results:
            line = f"{message.remittance_id}: {message.status.value}"
            if message.failure_reason:
                line += f" ({message.failure_reason})"
            print(line)
    finally:
        db.close()


if __name__ == "__main__":
    main()
