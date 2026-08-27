VALID_KYC = {
    "full_name": "Alice Sender",
    "date_of_birth": "1990-01-01",
    "nationality": "South African",
    "identification_number": "8001015009087",
    "residential_address": "1 Long Street, Cape Town",
    "mobile_number": "+27000000001",
    "email_address": "sender@example.com",
    "source_of_funds": "Salary",
}


def test_status_before_submission_is_not_submitted(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/kyc/me/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_submitted"


def test_submit_kyc_sets_pending_status(client, register_and_login):
    headers = register_and_login()
    resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["identification_number"] == VALID_KYC["identification_number"]

    status_resp = client.get("/kyc/me/status", headers=headers)
    assert status_resp.json()["status"] == "pending"


def test_identification_number_encrypted_at_rest(client, register_and_login):
    """NFR-08a: the raw ID number must never be stored in plaintext in the DB."""
    headers = register_and_login()
    client.post("/kyc", json=VALID_KYC, headers=headers)

    from sqlalchemy import text

    from tests.conftest import TestingSessionLocal
    from app.models.kyc import KYCApplication

    db = TestingSessionLocal()
    try:
        row = db.query(KYCApplication).first()
        raw_value = db.execute(
            text("SELECT identification_number FROM kyc_applications WHERE id = :id"), {"id": row.id}
        ).scalar_one()
        assert raw_value != VALID_KYC["identification_number"]
        assert row.identification_number == VALID_KYC["identification_number"]
    finally:
        db.close()


def test_non_admin_cannot_list_kyc_applications(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/kyc", headers=headers)
    assert resp.status_code == 403


def test_admin_can_approve_pending_application(client, register_and_login, admin_headers):
    headers = register_and_login()
    submit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    app_id = submit_resp.json()["id"]

    approve_resp = client.post(f"/kyc/{app_id}/approve", headers=admin_headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    status_resp = client.get("/kyc/me/status", headers=headers)
    assert status_resp.json()["status"] == "approved"


def test_admin_can_reject_pending_application_with_reason(client, register_and_login, admin_headers):
    headers = register_and_login()
    submit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    app_id = submit_resp.json()["id"]

    reject_resp = client.post(
        f"/kyc/{app_id}/reject", json={"rejection_reason": "ID document unclear"}, headers=admin_headers
    )
    assert reject_resp.status_code == 200
    body = reject_resp.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "ID document unclear"


def test_rejected_user_can_resubmit(client, register_and_login, admin_headers):
    headers = register_and_login()
    submit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    app_id = submit_resp.json()["id"]
    client.post(f"/kyc/{app_id}/reject", json={"rejection_reason": "bad ID"}, headers=admin_headers)

    resubmit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    assert resubmit_resp.status_code == 201
    assert resubmit_resp.json()["status"] == "pending"
    assert resubmit_resp.json()["rejection_reason"] is None


def test_cannot_resubmit_once_approved(client, register_and_login, admin_headers):
    headers = register_and_login()
    submit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    app_id = submit_resp.json()["id"]
    client.post(f"/kyc/{app_id}/approve", headers=admin_headers)

    resubmit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    assert resubmit_resp.status_code == 409


def test_cannot_approve_non_pending_application(client, register_and_login, admin_headers):
    headers = register_and_login()
    submit_resp = client.post("/kyc", json=VALID_KYC, headers=headers)
    app_id = submit_resp.json()["id"]
    client.post(f"/kyc/{app_id}/approve", headers=admin_headers)

    second_approve = client.post(f"/kyc/{app_id}/approve", headers=admin_headers)
    assert second_approve.status_code == 409


def test_require_approved_kyc_dependency_blocks_unapproved_user(client, register_and_login):
    """FR-09/FR-09a guard, exercised directly since no remittance/cash-out
    endpoint exists yet in this slice."""
    from fastapi import HTTPException
    import pytest

    from app.core.deps import require_approved_kyc

    headers = register_and_login()
    resp = client.get("/users/me", headers=headers)
    user_id = resp.json()["id"]

    from tests.conftest import TestingSessionLocal
    from app.models.user import User

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        with pytest.raises(HTTPException) as exc_info:
            require_approved_kyc(current_user=user)
        assert exc_info.value.status_code == 403
    finally:
        db.close()
