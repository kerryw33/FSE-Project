# XRPL-Based FX Remittance Platform (RLUSD)

UCT ECO5040W group project. Prototype cross-border remittance platform: ZAR
in, RLUSD settlement on the XRP Ledger Testnet, simulated fiat cash-out.

## Status

Implemented so far (FR-01–FR-09a): registration, login/logout, profile
view/update, KYC submission + status, admin KYC review, and the
`require_approved_kyc` guard that future remittance/cash-out endpoints will
depend on. Everything else in `functional_requirements.pdf` (beneficiaries,
quotes, cash-in, queue/settlement, wallet, cash-out, fee/limit admin) is not
built yet.

## Stack

FastAPI + SQLAlchemy + SQLite (dev), per `basics.pdf`'s recommendations.
Passwords hashed with bcrypt via passlib. Sessions are opaque bearer tokens
stored in a `sessions` table (not JWT) so logout can just revoke a row.
Sensitive KYC fields (identification number) are encrypted at rest with
Fernet, key supplied via `KYC_ENCRYPTION_KEY` env var, kept out of the
database per NFR-04/NFR-08a.

## Key assumptions (to carry into the technical specification)

- **Roles (FR-04)**: `UserRole` is `CUSTOMER` or `ADMIN`. A customer account
  acts as both sender and recipient depending on context, not as two
  separate identities. Admin accounts are provisioned via
  `scripts/create_admin.py`, never via self-registration.
- **KYC resubmission**: one KYC row per user. A rejected (or still pending)
  application can be resubmitted, which overwrites the details and resets
  status to `pending`. Once `approved`, resubmission is blocked (409).

## Running locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set KYC_ENCRYPTION_KEY, see comment in the file
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

Create an admin account:

```bash
python -m scripts.create_admin "Admin Name" admin@example.com +27000000000 <password>
```

## Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```
