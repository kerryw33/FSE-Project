import os

os.environ.setdefault("KYC_ENCRYPTION_KEY", "wSMlvW7WkYVBLl9x8-x0LICU95hqHRvA1LGjXhh2eKI=")
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
