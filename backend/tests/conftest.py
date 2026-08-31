import os

os.environ.setdefault("KYC_ENCRYPTION_KEY", "wSMlvW7WkYVBLl9x8-x0LICU95hqHRvA1LGjXhh2eKI=")
os.environ.setdefault("XRPL_KEY_ENCRYPTION_KEY", "pkTualMz1bJ2RUeoHK5dHWCE-9kuVxqWxc_fB7KQRK0=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def _fresh_database():
    from app.services.bootstrap import seed_defaults

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def register_and_login(client):
    def _do(email="sender@example.com", mobile="+27000000001", password="StrongPass123"):
        client.post(
            "/auth/register",
            json={
                "full_name": "Test Sender",
                "email": email,
                "mobile_number": mobile,
                "password": password,
            },
        )
        resp = client.post("/auth/login", json={"email": email, "password": password})
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _do


@pytest.fixture
def admin_headers(client, db_session_factory=TestingSessionLocal):
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    db = TestingSessionLocal()
    admin = User(
        full_name="Admin User",
        email="admin@example.com",
        mobile_number="+27000000099",
        password_hash=hash_password("AdminPass123"),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.commit()
    db.close()

    resp = client.post("/auth/login", json={"email": "admin@example.com", "password": "AdminPass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def approved_sender(client, admin_headers):
    """Registers a user, submits KYC, and has the admin approve it -
    returning auth headers for a sender who can now pass require_approved_kyc."""

    def _do(email="sender@example.com", mobile="+27000000001", password="StrongPass123"):
        client.post(
            "/auth/register",
            json={"full_name": "Approved Sender", "email": email, "mobile_number": mobile, "password": password},
        )
        login = client.post("/auth/login", json={"email": email, "password": password})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        client.post(
            "/kyc",
            json={
                "full_name": "Approved Sender",
                "date_of_birth": "1990-01-01",
                "nationality": "South African",
                "identification_number": "8001015009087",
                "residential_address": "1 Long Street, Cape Town",
                "mobile_number": mobile,
                "email_address": email,
                "source_of_funds": "Salary",
            },
            headers=headers,
        )
        application_id = client.get("/kyc/me", headers=headers).json()["id"]
        client.post(f"/kyc/{application_id}/approve", headers=admin_headers)

        return headers

    return _do


@pytest.fixture
def platform_wallet_row():
    """Inserts a fake PlatformWallet row directly - there's no API surface
    for it (it's provisioned via scripts/setup_platform_wallet.py in
    reality), and settlement needs one to exist."""
    from app.models.platform_wallet import PlatformWallet

    db = TestingSessionLocal()
    try:
        wallet = PlatformWallet(
            classic_address="rFAKEPLATFORM0000000000000000000",
            secret="sFAKEPLATFORMSECRET",
            trustline_established=True,
        )
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        return wallet
    finally:
        db.close()


@pytest.fixture
def mock_xrpl(monkeypatch):
    """Replaces every live XRPL Testnet call (faucet funding, TrustSet,
    Payment) with fast, deterministic fakes, so the default test run
    never depends on network access or real UCTUSD liquidity.

    Returns a mutable dict a test can flip to `should_fail: True` to
    simulate a failed on-chain Payment (e.g. insufficient liquidity),
    exercising FR-24's failure path with a controlled, repeatable error.
    """
    import itertools
    from types import SimpleNamespace

    counter = itertools.count(1)

    def fake_generate_and_fund_wallet():
        n = next(counter)
        return SimpleNamespace(classic_address=f"rFAKERECIPIENT{n}", seed=f"sFAKESEED{n}")

    def fake_establish_trustline(wallet):
        return f"FAKE_TRUSTLINE_TX_{wallet.classic_address}"

    state = {"should_fail": False, "fail_reason": "tecUNFUNDED_PAYMENT"}

    def fake_submit_payment(from_seed, destination_address, amount):
        if state["should_fail"]:
            raise RuntimeError(f"Payment failed: {state['fail_reason']}")
        return f"FAKE_PAYMENT_TX_{destination_address}_{amount}"

    monkeypatch.setattr("app.services.recipient_wallet.generate_and_fund_wallet", fake_generate_and_fund_wallet)
    monkeypatch.setattr("app.services.recipient_wallet.establish_trustline", fake_establish_trustline)
    monkeypatch.setattr("app.services.settlement.submit_issued_currency_payment", fake_submit_payment)

    return state


@pytest.fixture
def settle_a_remittance(client, approved_sender, platform_wallet_row, mock_xrpl, admin_headers):
    """End-to-end: an approved sender sends a remittance to a newly
    registered recipient, cash-in is confirmed, and settlement runs
    successfully (mocked XRPL calls). Returns a function yielding
    (recipient_headers, sender_headers, settled_remittance_json).
    """

    def _do(
        zar_amount="1000.00",
        recipient_email="recipient@example.com",
        recipient_mobile="+27000000777",
        sender_email="sender@example.com",
        sender_mobile="+27000000001",
    ):
        sender_headers = approved_sender(email=sender_email, mobile=sender_mobile)

        client.post(
            "/auth/register",
            json={
                "full_name": "Recipient",
                "email": recipient_email,
                "mobile_number": recipient_mobile,
                "password": "RecipientPass123",
            },
        )
        recipient_login = client.post(
            "/auth/login", json={"email": recipient_email, "password": "RecipientPass123"}
        )
        recipient_headers = {"Authorization": f"Bearer {recipient_login.json()['access_token']}"}

        ben_resp = client.post(
            "/beneficiaries",
            json={
                "full_name": "Recipient",
                "email_address": recipient_email,
                "country": "South Africa",
                "payout_currency": "USD",
                "relationship_to_sender": "Friend",
            },
            headers=sender_headers,
        )
        beneficiary_id = ben_resp.json()["id"]

        quote_resp = client.post(
            "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": zar_amount}, headers=sender_headers
        )
        remittance_id = quote_resp.json()["id"]

        client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "bank_transfer"}, headers=sender_headers)
        client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)
        client.post("/admin/settlement/run", headers=admin_headers)

        remittances = client.get("/remittances/me", headers=sender_headers).json()
        settled = next(r for r in remittances if r["id"] == remittance_id)

        return recipient_headers, sender_headers, settled

    return _do
