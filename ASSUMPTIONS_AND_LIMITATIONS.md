# Assumptions and Limitations

Compiled from design decisions made while building the backend, for direct
use in the technical specification's "Assumptions and Limitations" section
(project_brief.pdf, deliverable i). Organized to roughly follow the FR
sections in `functional_requirements.pdf`.

## Registration & Authentication (FR-01–04a)

- **Roles**: `UserRole` is `CUSTOMER` or `ADMIN`. A customer account acts as
  both sender and recipient depending on context (sending a remittance vs.
  being someone else's beneficiary), not as two separate identities. Admin
  accounts are provisioned out-of-band (`scripts/create_admin.py`), never
  via self-registration.
- **Session mechanism, not JWT**: logout (FR-02a) uses opaque bearer tokens
  stored in a `sessions` table rather than JWT. Neither project document
  mandates a token mechanism - FR-02a just requires that logout "terminate
  their session." A stateless JWT can't actually be revoked before its own
  expiry without a blacklist table or a token-version counter, which ends
  up being the same shape as this table anyway, plus signing/claims
  overhead that only pays off when multiple independent services need to
  verify a token without a callback - not the case for this single-backend
  project. See `app/models/session.py` for the full rationale.

## KYC (FR-05–09a)

- **Resubmission model**: one KYC row per user, not a history table. A
  rejected (or still-pending) application can be resubmitted, overwriting
  the details and resetting status to `pending`. Once `approved`,
  resubmission is blocked.
- **KYC-before-value-leaves-the-platform** (stated directly in the FR
  document as an assumption we adopted as-is): both senders and recipients
  need approved KYC before moving value *out* of the platform - senders
  before sending (FR-09), recipients before cashing out (FR-09a). A
  recipient may hold RLUSD without KYC, just not cash out.

## Beneficiary Management (FR-10–12c)

- **Linking mechanism** (the FR document explicitly flags this as an
  undecided design choice needing documentation): auto-match on an
  existing registered account by mobile/email, not an invite-to-register
  flow. Matching happens immediately at beneficiary creation, and
  retroactively the moment a matching account registers later if no match
  existed yet.
- **Wallet provisioning is two-phase**: the internal ledger row
  (`RecipientWallet`) is created immediately on linking - fast, DB-only, no
  network calls. The real XRPL account (address + encrypted key) is
  generated lazily on that recipient's *first actual settlement*, not at
  linking time, so registration/beneficiary endpoints never block on the
  Testnet faucet.

## Quote, Fees & Limits (FR-13–17)

- **Exchange rate**: a static configured value (`USD_ZAR_RATE` env var),
  not a live public API - one of the three options the brief explicitly
  permits ("public API, mock service, or configured rate table"). Unlike
  fees, there's currently no admin API to change it at runtime; changing
  it means editing `.env` and restarting.
- **Fee model**: a single admin-editable `FeeConfig` row (fixed fee, %
  fee, FX margin, cash-out fee), not a versioned/historical table.
- **Limit tier is derived, not stored**: `tier_for_user()` maps
  KYC-approved → `verified`, everything else → `unverified`, rather than a
  separate field on `User`. In practice `unverified` is never reached
  through the quote endpoint since `require_approved_kyc` already blocks
  unapproved senders earlier.
- **A quote consumes the limit immediately at creation**, not only once
  cash-in is confirmed - FR-16/17 gate "the transaction proceeding," and
  there's no expiry/cancellation mechanism for a quote a sender never
  follows through on. A quote a sender abandons still counts against that
  day's/month's allowance.

## Simulated Cash-In / Queue & Settlement (FR-18–26)

- **One row, extended in place**: `Remittance` carries the whole lifecycle
  (`quoted` → `cash_in_pending` → `cash_in_confirmed` → `settlement_queued`
  → `settled`/`settlement_failed`) as one evolving record rather than
  separate tables per stage.
- **Message queue is Redis Streams** (`app/services/settlement.py`), per
  basics.pdf's explicit recommendation ("lowest-friction options to stand
  up locally"). A single consumer group (`settlement_workers`, one
  consumer, matching FR-22's singular "a settlement worker") reads
  entries and acks them once processed. The durable record of
  status/outcome/tx-hash still lives in the `SettlementMessage`/
  `Remittance` DB rows regardless of queue technology - Redis is the
  transport, not the source of truth, which is why switching from the
  earlier DB-polling prototype only touched one service file and no
  correctness logic (`process_settlement_message`) at all.
- **No PEL reclaim / redelivery-on-crash**: if a worker died mid-processing
  after Redis delivered it a message but before acking, that entry would
  sit in the consumer group's pending-entries list rather than being
  automatically handed to another consumer (`XCLAIM`/`XAUTOCLAIM` isn't
  implemented). Recovery in that scenario would need manual inspection -
  in practice this project only ever runs one consumer, so it's a real
  gap rather than a mitigated one.
- **No automatic retry** for a failed settlement message - an admin must
  explicitly retry it (`POST /admin/settlement/{id}/retry`), which resets
  the DB row and re-publishes to the stream (a failed-and-acked message
  is not redelivered by Redis on its own). There's no backoff/scheduling
  logic.

## Recipient Wallet (FR-27–29)

- **Wallet architecture is a hybrid**, not the brief's pure "one platform
  wallet + internal ledger" option: a single platform treasury wallet
  (`PlatformWallet`, exactly one row) holds the team's UCTUSD/RLUSD
  liquidity, but each recipient still gets a real, platform-controlled
  custodial XRPL Testnet account. This was necessary to reconcile two
  things: FR-22/23 require a genuine, individually attributable on-chain
  Payment + tx hash per remittance (impossible if the platform wallet just
  pays itself), while course-provided liquidity is distributed to one
  wallet per team. XRP funding and TrustLines are free/unlimited via the
  faucet regardless of how many recipient accounts exist; only the
  RLUSD/UCTUSD token liquidity is scarce and centralized.
- **`RecipientWallet.balance` is a cached value**, not a live ledger query
  - updated by the settlement worker (FR-26) and cash-out (FR-30/32). It
    should always match the real on-chain balance since nothing else moves
    funds through that account, but a live discrepancy would only be
    caught by manually querying the ledger, not by the API itself.
- **Currency/issuer are config values** (`XRPL_ISSUER_ADDRESS`,
  `XRPL_CURRENCY_CODE`), currently pointed at the course-provided UCTUSD
  fallback token rather than the official RLUSD issuer (per basics.pdf's
  "RLUSD vs our own IOU" guidance) - switching is a one-line `.env` change,
  verified concretely rather than just structurally.
- Discovered during setup: the UCTUSD issuer auto-grants 100,000 UCTUSD to
  a wallet the moment it establishes a TrustLine - a platform wallet isn't
  actually blocked on the course's manual liquidity distribution to start
  testing settlement end-to-end.

## Simulated Cash-Out (FR-30–32, FR-35)

- **Supported fiat currencies**: USD and ZAR only, not an open-ended set.
- **ZAR cash-out uses the same configured USD/ZAR rate as remittances, but
  without the FX margin** - FR-31 only names "the applicable exchange
  rate" and the cash-out fee, unlike the remittance quote which explicitly
  layers on a margin.
- **Cash-out completion is a pure status transition**, not a second
  on-chain leg returning RLUSD from the recipient's account back to the
  platform treasury. FR-32 only requires the cash-out itself be simulated
  via status tracking ("requested, approved, completed, or failed"); a
  real reverse transfer was considered and deliberately dropped to keep
  the failure surface and scope contained.
- **RLUSD is reserved (debited) at request time**, not at completion -
  prevents a recipient overdrawing their balance via concurrent cash-out
  requests. A failed request refunds the reserved amount back.

## Security (NFR-03–06, NFR-08–08a)

- **Two separate Fernet keys**: `KYC_ENCRYPTION_KEY` for KYC PII (identification
  number) and a distinct `XRPL_KEY_ENCRYPTION_KEY` for XRPL private keys
  (both the platform wallet's and every recipient wallet's) - a leak of one
  category's key doesn't expose the other's ciphertext.
- **No custom application logging exists** beyond uvicorn's default access
  log (method/path/status, no request bodies) - NFR-06 currently holds by
  construction rather than by an explicit redaction filter; verified by
  grepping actual server logs for known secrets/passwords/ID numbers, not
  just assumed.

## Database / Infrastructure

- **No migration tool (Alembic)** - schema is managed via SQLAlchemy's
  `create_all`, which creates missing tables but never alters existing
  ones. This already caused one real incident during development (adding
  columns to `remittances` silently didn't apply until the table was
  manually dropped and recreated) and will need replacing with real
  migrations once the schema stabilises, per the comment in `app/main.py`.
- **SQLite for development** - fine at the tested scale (50 concurrent
  users, 0 failures - see `PERFORMANCE_TESTING.md`), but SQLite's
  single-writer model would likely become a real bottleneck at higher
  concurrent write volume than was tested; Postgres would be the
  production-equivalent choice if that mattered.

## Testing

- **All XRPL network calls (faucet funding, TrustSet, Payment) are mocked**
  in the automated pytest suite (`tests/conftest.py`'s `mock_xrpl`
  fixture) so it runs fast and deterministically. Real integration is
  verified separately and manually against the live Testnet (see commit
  history and `backend/scripts/smoke_test.sh`), not by the automated suite
  itself.
- **Redis is real (not mocked) in the test suite** - it's fast and local,
  unlike the XRPL Testnet, so there's no benefit to mocking it. Tests
  point at a dedicated Redis DB number (15, flushed before every test) so
  they never collide with dev/demo queue data in DB 0. This does mean the
  test suite now has a hard runtime dependency on a local Redis instance
  being reachable - it wasn't required before this change.
- **Performance testing deliberately excludes XRPL settlement** from the
  concurrent-user load test (`perf/locustfile.py`) - mixing in real network
  calls would measure Testnet/faucet latency rather than this API's own
  performance. Settlement timing is benchmarked separately
  (`scripts/benchmark_settlement.py`).
