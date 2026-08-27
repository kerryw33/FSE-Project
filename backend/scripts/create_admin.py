"""Provision an administrator account.

Admins are never created via the public /auth/register endpoint (that would
let anyone self-elevate); run this script instead:

    python -m scripts.create_admin "Admin Name" admin@example.com +27000000000 <password>
"""

import sys

sys.path.insert(0, ".")

from app.core.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        raise SystemExit(1)

    full_name, email, mobile_number, password = sys.argv[1:5]

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"A user with email {email} already exists.")
            raise SystemExit(1)

        admin = User(
            full_name=full_name,
            email=email,
            mobile_number=mobile_number,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        print(f"Created admin user {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
