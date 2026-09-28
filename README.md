# XRPL-Based FX Remittance Platform (UCTUSD on Testnet)

UCT ECO5040W **Group 3** (Annita Ngoma, Karabo Tigedi, Kerry-Lynn Whyte, Lilitha Mzamo, Nikola Milosavljevic).

This repository (`kerryw33/FSE-Project`) is the main source for the project. The API here is the patched system (quote TTL and cancel, hashed sessions, Alembic, settlement outbox / PEL reclaim, honest wallet balances, UCTUSD burn). **138** pytest tests collected on this tree.

Academic prototype only: simulated ZAR cash-in, UCTUSD settlement on the XRP Ledger **Testnet**, simulated fiat cash-out with on-chain burn to issuer. No real customer funds, no Mainnet credentials.

## Reports (deliverable i)

Compiled PDFs (run `powershell -File docs/reports/compile.ps1`):

- [Business and technical specification](docs/reports/spec/business_technical_specification.pdf) (official 10–15 page spec)
- [Group rationale](docs/reports/rationale/group_rationale.pdf)


## Stack

FastAPI + SQLAlchemy + SQLite (dev). Redis Streams for settlement transport (DB row is source of truth). `xrpl-py` against Testnet JSON-RPC. USD/ZAR from [open.er-api.com](https://open.er-api.com/v6/latest/USD), cached 5 minutes, `.env` fallback (`USD_ZAR_RATE`). Interactive API: `http://127.0.0.1:8000/docs`.

## Running locally, step by step

You need **Python 3.10+**, **Node.js 18+**, **Redis 5+** and **git**. Commands are given for **macOS/Linux** and **Windows (PowerShell)**; where they differ, both are shown.

You will end up with three terminals open: the **API**, the **web UI**, and a spare one for scripts.

### 1. Get the code

```bash
git clone https://github.com/kerryw33/FSE-Project.git
cd FSE-Project
```

### 2. Start Redis

Redis must be listening on `localhost:6379` before the API starts, or confirmed cash-ins are never picked up for settlement.

- macOS: `brew install redis` then `brew services start redis`
- Windows: **Memurai**, **Docker** (`docker run -d -p 6379:6379 redis`) or **WSL** `redis-server`

### 3. Set up the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # Windows: Copy-Item .env.example .env
```

Your prompt should now start with `(.venv)`. If you use conda, run `conda deactivate` first so the right Python is used.

### 4. Add two encryption keys to `.env`

Run this **twice**. Each run prints one key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the first as `KYC_ENCRYPTION_KEY=` and the second as `XRPL_KEY_ENCRYPTION_KEY=` in `backend/.env`. They must be different. Keep the trailing `=`.

### 5. Create the database

Do this **before** step 6. `create_admin` builds tables on its own, and a database created that way will not migrate.

```bash
alembic upgrade head
```

### 6. Create an admin account

Admins cannot sign up through the website.

```bash
python -m scripts.create_admin "Admin Name" admin@example.com +27000000000 <password>
```

### 7. Create the platform treasury wallet

Once per database:

```bash
python -m scripts.setup_platform_wallet
```

This creates a new XRPL **Testnet** account (funded with test XRP by the faucet), sets its TrustLine to the UCTUSD issuer, stores its key encrypted in your database, and prints its **address**. Keep the address. Each copy of the app gets its own treasury; nobody else's wallet is reused.

### 8. Start the API (terminal 1)

```bash
python -m uvicorn app.main:app --reload
```

Leave it running. API docs: http://127.0.0.1:8000/docs

### 9. Start the web UI (terminal 2)

```bash
cd frontend          # from the repository root
npm install
npm run dev
```

Open http://localhost:5173. Point `VITE_API_URL` at the API if it is not `http://127.0.0.1:8000`.

### 10. Check the treasury holds UCTUSD

Log in with the admin account and open **Admin → Platform wallet**. Settlement only works once the treasury holds UCTUSD.

- About **100,000 UCTUSD**: you are ready.
- **0** after a minute or two: send the address from step 7 to Marc for the **100,000 UCTUSD** grant, and wait for it. Use the official course token only; do **not** mint your own.

Until the treasury is funded, settlement fails with an "Insufficient UCTUSD liquidity" reason. Once it is funded, use **Retry** on the admin Settlement page.

### 11. Try the full flow

1. Register a **sender** and a **recipient** (separate browser tabs keep separate logins). Both submit KYC.
2. As admin, approve both on **Admin → KYC**.
3. As the sender, add the recipient as a beneficiary using the **same mobile number or email** they registered with. It shows **Linked**.
4. Lock a quote on **Send**, then **Cash in**.
5. As admin: **Cash-in → Confirm cash-in**, then **Settlement → Run settlement worker**. The first settlement to a new recipient creates their Testnet account and can take up to a minute.
6. The sender's **Track** page and the recipient's **Wallet** show the transaction hash. Open it on https://testnet.xrpl.org.
7. As the recipient, request a **Cash-out**. As admin, **Approve**, then **Complete** (this burns the UCTUSD by paying the issuer).

The worker can also be run from a terminal instead of the admin button:

```bash
python -m scripts.run_settlement_worker
```

### Token details

| | |
|---|---|
| Symbol | UCTUSD |
| Currency | `5543545553440000000000000000000000000000` |
| Issuer | `rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5` |
| Distributor | `rsWPX7FKwnfk6enosumAzEuTs5Y12Steq4` |
| Explorer | https://testnet.xrpl.org/token/5543545553440000000000000000000000000000.rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5 |
| Source | https://github.com/marclevin/UCTUSD |

Both platform and customer wallets need a TrustLine before Payment. Burn = send UCTUSD to the issuer. The official RLUSD faucet is 10 / 24h; use UCTUSD until Marc says migrate.

### Troubleshooting

- **`command not found: ..venvScriptsActivate.ps1`**: that is the Windows command. On macOS/Linux use `source .venv/bin/activate`.
- **`alembic upgrade` fails on an existing database**: databases created only with `create_all` (no `alembic_version` table) cannot migrate. Delete that `fx_platform.db` and start again from step 5. Never delete a database whose treasury you want to keep: its file holds the treasury's encrypted private key.
- **Settlement never happens**: check Redis is running (step 2).
- **"Beneficiary is not linked"**: the recipient must register with the same mobile number or email the sender used.
- **Never commit** `backend/.env` or `fx_platform.db`. Together they give full control of the treasury wallet.

## Tests

Redis must be running. XRPL calls are mocked; tests use Redis DB 15.

```bash
cd backend
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
python -m pytest -q
```

## Optional: public URL

`render.yaml` + `deploy/` host the UI and API on one Render link (useful for sharing on WhatsApp). Not required for the course.

## Performance numbers

[`PERFORMANCE_TESTING.md`](PERFORMANCE_TESTING.md) is deliverable iv. HTTP load was **re-run on this fork on 2026-09-07** (50 users, 60 s, Windows): 2,218 requests, 0 failures, **37.2 req/s**, login median **850 ms** (bcrypt). Charts: [`backend/perf/results/charts.html`](backend/perf/results/charts.html). Live XRPL settlement on the same day: five Testnet Payments, **5/5**, **17.5 s/tx** avg (enqueue **29.2 msg/s** on this host). A larger re-run on **2026-09-24** settled **15/15** Testnet Payments at **15.1 s/tx** average.

