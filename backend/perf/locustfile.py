"""Load test for NFR-01 (response time < 2s), NFR-02 (stable under ~50
concurrent users), and the Performance Testing Results deliverable
(API response times, requests/sec, success/failure rates under load).

Run against scripts/seed_synthetic_users.py's output - each simulated
Locust user checks out one distinct synthetic sender account so
concurrent virtual users aren't contending over the same account/session
(that would conflate our own limit/session logic with raw throughput).

Deliberately excludes /admin/settlement/run and anything that lazily
provisions a real XRPL account - those make live Testnet network calls,
which would measure faucet/ledger latency rather than this API's own
performance. That's measured separately by scripts/benchmark_settlement.py.

Usage:
    python -m scripts.seed_synthetic_users 50
    locust -f perf/locustfile.py --host=http://127.0.0.1:8000 \
        --users 50 --spawn-rate 10 --run-time 60s --headless \
        --csv=perf/results/run1 --html=perf/results/run1.html
"""

import itertools
import json
import random
import threading

from locust import HttpUser, between, task

with open("perf/synthetic_users.json") as f:
    _ACCOUNTS = json.load(f)

_account_cycle = itertools.cycle(_ACCOUNTS)
_account_lock = threading.Lock()


def _checkout_account():
    with _account_lock:
        return next(_account_cycle)


class RemittancePlatformUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        account = _checkout_account()
        self.beneficiary_id = account["beneficiary_id"]

        resp = self.client.post(
            "/auth/login",
            json={"email": account["email"], "password": account["password"]},
            name="/auth/login",
        )
        token = resp.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(3)
    def view_profile(self):
        self.client.get("/users/me", name="/users/me")

    @task(2)
    def view_kyc_status(self):
        self.client.get("/kyc/me/status", name="/kyc/me/status")

    @task(2)
    def view_limits(self):
        self.client.get("/limits/me", name="/limits/me")

    @task(2)
    def list_beneficiaries(self):
        self.client.get("/beneficiaries", name="/beneficiaries")

    @task(2)
    def view_wallet(self):
        self.client.get("/wallet/me", name="/wallet/me")

    @task(3)
    def create_quote(self):
        zar_amount = round(random.uniform(10, 100), 2)
        self.client.post(
            "/remittances",
            json={"beneficiary_id": self.beneficiary_id, "zar_amount": f"{zar_amount:.2f}"},
            name="/remittances [POST]",
        )
