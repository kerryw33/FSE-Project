# Performance Testing Results

Run 2026-08-31 against the FastAPI backend running locally (`uvicorn
app.main:app`, SQLite, single process) on the author's machine — not a
production-equivalent host, so treat absolute numbers as indicative rather
than a capacity guarantee, but the relative comparisons (which endpoints are
slow, what dominates settlement time) hold regardless of hardware.

## 1. API load test (NFR-01, NFR-02)

**Setup**: 50 synthetic KYC-approved sender accounts (`scripts/seed_synthetic_users.py`,
project_brief.pdf's "generate synthetic users" note), each with its own
beneficiary and raised remittance limits so the run measures API performance
rather than getting gated by business-rule limits (already covered by the
pytest suite). Locust (`perf/locustfile.py`), 50 concurrent users, spawn
rate 10/s, 60s run, hitting a realistic mix of the read-heavy endpoints
(profile, KYC status, limits, beneficiaries, wallet) plus quote creation
(the one write in the mix). Settlement processing and anything touching the
live XRPL Testnet was deliberately excluded — see §2.

**Result: 2,324 requests, 0 failures, 39.3 req/s aggregate throughput.**

| Endpoint | Requests | Median (ms) | Avg (ms) | p95 (ms) | p99 (ms) | Max (ms) |
|---|---:|---:|---:|---:|---:|---:|
| `POST /auth/login` | 50 | 400 | 396 | 430 | 470 | 467 |
| `GET /users/me` | 479 | 6 | 6.8 | 13 | 18 | 106 |
| `GET /kyc/me/status` | 273 | 5 | 7.4 | 16 | 30 | 95 |
| `GET /limits/me` | 353 | 8 | 9.5 | 18 | 23 | 80 |
| `GET /beneficiaries` | 329 | 6 | 8.2 | 15 | 24 | 93 |
| `GET /wallet/me` | 344 | 8 | 9.0 | 17 | 22 | 120 |
| `POST /remittances` (quote) | 496 | 11 | 12.8 | 22 | 27 | 47 |
| **Aggregated** | 2,324 | 8 | 17.5 | 20 | 400 | 467 |

**NFR-01 (response within 2s under normal conditions):** met with wide
margin — every endpoint's p99 is under half a second, and the slowest
individual request across the whole run (467ms, a login) is still well
inside the 2s budget.

**NFR-02 (stable under ~50 concurrent users):** met — zero failures across
2,324 requests, throughput held steady across the full run (no degradation
between the three progress snapshots Locust printed during the run).

**Bottleneck identified — login latency:** `/auth/login` is ~50x slower
than every other endpoint (~400ms vs ~7-13ms median). This is bcrypt
password verification, which is deliberately expensive by design (NFR-03) -
not a defect, but worth knowing it's the practical ceiling on login
throughput specifically. It's not a concern at this scale (50 concurrent
logins still resolved in under half a second each) but would be the first
place to look if login ever needed to scale to a much higher rate (e.g.
a configurable bcrypt work factor, or moving to a session-token refresh
model that logs in less often).

## 2. Message-queue throughput and RLUSD settlement time

Measured separately from the HTTP load test (`scripts/benchmark_settlement.py`)
because settlement makes real network calls to the XRP Ledger Testnet -
mixing that into the concurrent-user run would measure Testnet/faucet
latency rather than this API's own performance.

Re-measured 2026-09-01 after swapping the settlement queue from a
DB-polling table to Redis Streams (basics.pdf's recommendation) - enqueue
now does a DB write *and* a Redis `XADD` round-trip, so the throughput
number below is a bit lower than an earlier DB-only measurement, which is
expected and not a regression to worry about.

| Metric | Result |
|---|---:|
| Message-queue enqueue throughput (Redis Streams) | 200 messages in 0.387s → **517 msg/s** |
| RLUSD/UCTUSD settlement processing time | 5 real Testnet transactions in 61.9s → **12.4s/transaction avg** |
| Settlement success rate | 5/5 (100%) |

**Bottleneck identified — XRPL ledger consensus time:** enqueueing (a
SQLite write plus a Redis `XADD`) is fast and not a concern at this
project's scale. Settlement is a different story: each transaction has to
be submitted and then wait for XRPL Testnet to close and validate a ledger
(`submit_and_wait`) before the API considers it confirmed - the XRP Ledger
targets a ~3-5s ledger close time, so a handful of seconds per transaction
is inherent to using a real blockchain for settlement, not something the
application code can optimize away. The ~12s average also reflects real
Testnet variability (congestion, retries against `LastLedgerSequence`)
between runs - an earlier run on 2026-08-31 saw ~17s/transaction with the
same code, purely due to network conditions that day. Practical
implication: the settlement worker's throughput ceiling is roughly the
ledger's own transaction rate, not anything in `app/services/settlement.py`
- if remittance volume ever needed to exceed that, the mitigation is
standard queue-worker scaling (adding more consumers to the
`settlement_workers` Redis consumer group) rather than optimizing the
per-transaction path, since each transaction already
does the minimum required work.

## 3. Concurrent-use behaviour and failure rates

- 0 failures across the entire 50-concurrent-user, 60s HTTP run (§1).
- 0 failures across 5/5 real settlement transactions (§2) - all landed
  `tesSUCCESS` on the first attempt, no retries needed.
- Failure-handling logic itself (FR-24: a failed settlement must not credit
  the recipient) is exercised deterministically in the automated test suite
  (`backend/tests/test_settlement.py`) with a mocked XRPL failure, rather
  than performance-tested live - that path isn't something to load-test, it's
  a correctness property already covered by 82 passing pytest tests.

## How to reproduce

```bash
brew services start redis                       # if not already running

cd backend
source .venv/bin/activate
python -m scripts.setup_platform_wallet        # once per environment
python -m scripts.seed_synthetic_users 50
uvicorn app.main:app &                          # or --reload for dev
locust -f perf/locustfile.py --host=http://127.0.0.1:8000 \
    --users 50 --spawn-rate 10 --run-time 60s --headless \
    --csv=perf/results/run1 --html=perf/results/run1.html
python -m scripts.benchmark_settlement 5
```

Full Locust output (per-request percentile breakdown, charts) is in
`backend/perf/results/run1.html` and the raw CSVs alongside it.
