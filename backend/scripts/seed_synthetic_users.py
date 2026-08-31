"""Seed synthetic, KYC-approved sender accounts (with a beneficiary each)
for performance testing (project_brief.pdf: "Generate synthetic users for
your performance tests and simulations").

Writes credentials to perf/synthetic_users.json for locustfile.py to
consume, and raises the 'verified' limit tier so quote creation during
the load test isn't gated by FR-16/17's daily/monthly limits - the load
test measures API performance, not limit-enforcement correctness (that's
already covered by the pytest suite).

Uses the service layer directly rather than the HTTP API, since seeding
30+ users through real requests would itself take a while and isn't part
of what's being measured.

    python -m scripts.seed_synthetic_users [count]
"""

import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, ".")

from app.core.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.beneficiary import Beneficiary  # noqa: E402
from app.models.kyc import KYCApplication, KYCStatus  # noqa: E402
from app.models.limit_tier import LimitTier, LimitTierKey  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.bootstrap import seed_defaults  # noqa: E402

OUTPUT_PATH = "perf/synthetic_users.json"
PASSWORD = "LoadTestPass123"


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_defaults(db)

        verified_tier = db.query(LimitTier).filter(LimitTier.tier_key == LimitTierKey.VERIFIED).first()
        verified_tier.daily_limit_zar = Decimal("100000000")
        verified_tier.monthly_limit_zar = Decimal("1000000000")
        db.add(verified_tier)
        db.commit()

        accounts = []
        for i in range(count):
            email = f"loadtest-sender-{i}@example.com"
            mobile = f"+2782{i:07d}"

            existing = db.query(User).filter(User.email == email).first()
            if existing is not None:
                beneficiary = db.query(Beneficiary).filter(Beneficiary.sender_id == existing.id).first()
                accounts.append({"email": email, "password": PASSWORD, "beneficiary_id": beneficiary.id})
                continue

            user = User(
                full_name=f"Load Test Sender {i}",
                email=email,
                mobile_number=mobile,
                password_hash=hash_password(PASSWORD),
                role=UserRole.CUSTOMER,
            )
            db.add(user)
            db.flush()

            kyc = KYCApplication(
                user_id=user.id,
                full_name=user.full_name,
                date_of_birth=date(1990, 1, 1),
                nationality="South African",
                identification_number=f"800101500{i:04d}",
                residential_address="1 Long Street, Cape Town",
                mobile_number=mobile,
                email_address=email,
                source_of_funds="Salary",
                status=KYCStatus.APPROVED,
                submitted_at=datetime.now(timezone.utc),
                reviewed_at=datetime.now(timezone.utc),
            )
            db.add(kyc)

            beneficiary = Beneficiary(
                sender_id=user.id,
                full_name=f"Beneficiary {i}",
                email_address=f"loadtest-beneficiary-{i}@example.com",
                country="South Africa",
                payout_currency="USD",
                relationship_to_sender="Friend",
            )
            db.add(beneficiary)
            db.commit()
            db.refresh(beneficiary)

            accounts.append({"email": email, "password": PASSWORD, "beneficiary_id": beneficiary.id})

        with open(OUTPUT_PATH, "w") as f:
            json.dump(accounts, f, indent=2)

        print(f"Seeded {len(accounts)} synthetic sender accounts -> {OUTPUT_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
