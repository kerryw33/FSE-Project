# XRPL-Based FX Remittance Platform (RLUSD)

UCT ECO5040W group project. Prototype cross-border remittance platform: ZAR
in, RLUSD/UCTUSD settlement on the XRP Ledger Testnet, simulated fiat
cash-out.

## Status

All functional requirements (FR-01 through FR-35, including lettered
sub-requirements) from `functional_requirements.pdf` are implemented and
tested - registration/login/logout/profile, KYC + admin review, beneficiary
management with auto-linking, quote/fee/limit calculation with admin config,
simulated cash-in, a Redis Streams settlement queue + worker that submits
real XRPL Payment transactions, the recipient's custodial wallet, sender
transaction history, and simulated cash-out with admin actioning. Not yet
done: the web front end (currently API-only, explorable via `/docs`) and the
performance-testing deliverable.

## Stack

FastAPI + SQLAlchemy + SQLite (dev), per `basics.pdf`'s recommendations.
Passwords hashed with bcrypt via passlib. Sessions are opaque bearer tokens
stored in a `sessions` table (not JWT) so logout can just revoke a row.
XRPL integration uses `xrpl-py` against the public Testnet JSON-RPC endpoint.
The settlement queue is Redis Streams (`redis-py`), per basics.pdf's
recommendation - requires a local Redis instance (`brew install redis`).

## Key assumptions (to carry into the technical specification)

- **Roles (FR-04)**: `UserRole` is `CUSTOMER` or `ADMIN`. A customer account
  acts as both sender and recipient depending on context, not as two
  separate identities. Admin accounts are provisioned via
  `scripts/create_admin.py`, never via self-registration.
- **KYC resubmission**: one KYC row per user. A rejected (or still pending)
  application can be resubmitted, which overwrites the details and resets
  status to `pending`. Once `approved`, resubmission is blocked (409).
- **Beneficiary linking (FR-12a/12c)**: auto-match on mobile/email against
  an existing account, either immediately at creation or retroactively when
  a matching account registers later - not an invite-to-register flow.
- **Wallet model**: a hybrid of the brief's two options. One platform
  treasury wallet (`PlatformWallet`) holds the team's UCTUSD/RLUSD liquidity;
  each recipient still gets a real, platform-controlled custodial XRPL
  Testnet account (`RecipientWallet`), generated lazily on first settlement.
  This lets FR-22/23 produce a genuine, individually attributable on-chain
  Payment + tx hash per remittance, while only the one treasury wallet needs
  scarce token liquidity (XRP funding and TrustLines are free/unlimited via
  the faucet). `RecipientWallet.balance` is a cached ledger view of that
  account's real on-chain balance.
- **Message queue**: Redis Streams (`app/services/settlement.py`), per
  basics.pdf's "lowest-friction options to stand up locally" recommendation.
  A consumer group (`settlement_workers`) reads entries and acks them after
  processing; the durable record of status/outcome/tx-hash (FR-23, NFR-09)
  stays in the `SettlementMessage`/`Remittance` DB rows regardless - Redis is
  purely the transport that wakes a consumer up, not the source of truth.
  No automatic redelivery-on-crash (PEL reclaim) is implemented; a stuck
  message needs the admin retry endpoint, which explicitly re-publishes.
- **Fee model**: a single admin-editable `FeeConfig` row (fixed fee, %
  fee, FX margin, cash-out fee) rather than a versioned/historical table.
- **Limit tiers (FR-16b)**: derived from KYC status (approved → `verified`,
  everything else → `unverified`) rather than a separately stored field.
- **Currency (basics.pdf, "RLUSD vs our own IOU")**: issuer address and
  currency code are config values (`XRPL_ISSUER_ADDRESS`,
  `XRPL_CURRENCY_CODE`), currently pointed at the course-provided UCTUSD
  fallback token - switching to real RLUSD is a one-line `.env` change.

## Running locally

```bash
brew install redis && brew services start redis   # once per machine

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set the two encryption keys, see comments in the file
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

Create an admin account:

```bash
python -m scripts.create_admin "Admin Name" admin@example.com +27000000000 <password>
```

Set up the platform's XRPL wallet (once per environment):

```bash
python -m scripts.setup_platform_wallet
```

Run one pass of the settlement worker (or POST `/admin/settlement/run`):

```bash
python -m scripts.run_settlement_worker
```

## Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

All XRPL network calls (faucet funding, TrustSet, Payment) are mocked in the
test suite (see the `mock_xrpl` fixture in `tests/conftest.py`) so it runs
fast and offline - the real integration is exercised manually against the
live Testnet instead. Redis, however, is real in tests - it's fast and
local, so there's no need to mock it. Tests use DB 15 (a conventional
scratch database), flushed before every test, kept separate from dev/demo
data in DB 0.

