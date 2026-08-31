from decimal import Decimal


def _linked_beneficiary_and_quote(client, sender_headers, recipient_email, recipient_mobile, zar_amount="1000.00"):
    client.post(
        "/auth/register",
        json={
            "full_name": "Recipient",
            "email": recipient_email,
            "mobile_number": recipient_mobile,
            "password": "RecipientPass123",
        },
    )
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
    assert ben_resp.json()["linked_user_id"] is not None

    quote_resp = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": zar_amount}, headers=sender_headers
    )
    return quote_resp.json()["id"]


def _confirmed_remittance(client, sender_headers, admin_headers, remittance_id):
    client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "bank_transfer"}, headers=sender_headers)
    return client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)


def test_confirm_cash_in_enqueues_settlement_message(client, approved_sender, admin_headers):
    """FR-20/FR-21: confirming cash-in queues settlement."""
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r1@example.com", "+27000000701")

    confirm_resp = _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)
    assert confirm_resp.json()["status"] == "settlement_queued"

    pending = client.get("/admin/settlement?message_status=pending", headers=admin_headers).json()
    assert any(m["remittance_id"] == remittance_id for m in pending)


def test_settlement_run_succeeds_and_credits_wallet(
    client, approved_sender, admin_headers, platform_wallet_row, mock_xrpl
):
    """FR-22/FR-23/FR-26: worker submits the Payment, records the tx hash,
    and credits the recipient's wallet balance."""
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r2@example.com", "+27000000702")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)

    run_resp = client.post("/admin/settlement/run", headers=admin_headers)
    assert run_resp.status_code == 200
    results = run_resp.json()
    assert len(results) == 1
    assert results[0]["status"] == "completed"

    remittances = client.get("/remittances/me", headers=sender_headers).json()
    settled = next(r for r in remittances if r["id"] == remittance_id)
    assert settled["status"] == "settled"
    assert settled["xrpl_settlement_tx_hash"] is not None

    recipient_login = client.post("/auth/login", json={"email": "r2@example.com", "password": "RecipientPass123"})
    recipient_headers = {"Authorization": f"Bearer {recipient_login.json()['access_token']}"}
    wallet = client.get("/wallet/me", headers=recipient_headers).json()
    assert Decimal(wallet["balance_rlusd"]) == Decimal(settled["rlusd_amount"])


def test_settlement_failure_does_not_credit_wallet(
    client, approved_sender, admin_headers, platform_wallet_row, mock_xrpl
):
    """FR-24: a failed on-chain Payment must not credit the recipient."""
    mock_xrpl["should_fail"] = True
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r3@example.com", "+27000000703")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)

    run_resp = client.post("/admin/settlement/run", headers=admin_headers)
    results = run_resp.json()
    assert results[0]["status"] == "failed"
    assert "tecUNFUNDED_PAYMENT" in results[0]["failure_reason"]

    remittances = client.get("/remittances/me", headers=sender_headers).json()
    settled = next(r for r in remittances if r["id"] == remittance_id)
    assert settled["status"] == "settlement_failed"

    recipient_login = client.post("/auth/login", json={"email": "r3@example.com", "password": "RecipientPass123"})
    recipient_headers = {"Authorization": f"Bearer {recipient_login.json()['access_token']}"}
    wallet = client.get("/wallet/me", headers=recipient_headers).json()
    assert Decimal(wallet["balance_rlusd"]) == Decimal("0")


def test_settlement_without_platform_wallet_fails_gracefully(client, approved_sender, admin_headers, mock_xrpl):
    """No platform_wallet_row fixture used here - simulates the real state
    before scripts/setup_platform_wallet.py has ever been run."""
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r4@example.com", "+27000000704")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)

    run_resp = client.post("/admin/settlement/run", headers=admin_headers)
    results = run_resp.json()
    assert results[0]["status"] == "failed"
    assert "Platform wallet is not set up" in results[0]["failure_reason"]


def test_processing_completed_message_again_does_not_double_credit(
    client, approved_sender, admin_headers, platform_wallet_row, mock_xrpl
):
    """FR-25: re-processing an already-COMPLETED message must not credit
    the wallet a second time."""
    from app.services.settlement import process_settlement_message
    from tests.conftest import TestingSessionLocal
    from app.models.settlement import SettlementMessage

    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r5@example.com", "+27000000705")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)
    client.post("/admin/settlement/run", headers=admin_headers)

    recipient_login = client.post("/auth/login", json={"email": "r5@example.com", "password": "RecipientPass123"})
    recipient_headers = {"Authorization": f"Bearer {recipient_login.json()['access_token']}"}
    balance_after_first = client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"]

    db = TestingSessionLocal()
    try:
        message = db.query(SettlementMessage).filter(SettlementMessage.remittance_id == remittance_id).first()
        process_settlement_message(db, message)
    finally:
        db.close()

    balance_after_second = client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"]
    assert balance_after_second == balance_after_first


def test_enqueue_settlement_is_idempotent(client, approved_sender, admin_headers):
    from app.services.settlement import enqueue_settlement
    from tests.conftest import TestingSessionLocal
    from app.models.remittance import Remittance
    from app.models.settlement import SettlementMessage

    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r6@example.com", "+27000000706")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)

    db = TestingSessionLocal()
    try:
        remittance = db.query(Remittance).filter(Remittance.id == remittance_id).first()
        enqueue_settlement(db, remittance)
        enqueue_settlement(db, remittance)
        count = db.query(SettlementMessage).filter(SettlementMessage.remittance_id == remittance_id).count()
        assert count == 1
    finally:
        db.close()


def test_retry_failed_settlement_message(client, approved_sender, admin_headers, platform_wallet_row, mock_xrpl):
    mock_xrpl["should_fail"] = True
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r7@example.com", "+27000000707")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)
    client.post("/admin/settlement/run", headers=admin_headers)

    failed = client.get("/admin/settlement?message_status=failed", headers=admin_headers).json()
    message_id = next(m["id"] for m in failed if m["remittance_id"] == remittance_id)

    retry_resp = client.post(f"/admin/settlement/{message_id}/retry", headers=admin_headers)
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "pending"

    mock_xrpl["should_fail"] = False
    run_resp = client.post("/admin/settlement/run", headers=admin_headers)
    assert run_resp.json()[0]["status"] == "completed"


def test_cannot_retry_non_failed_message(client, approved_sender, admin_headers, platform_wallet_row, mock_xrpl):
    sender_headers = approved_sender()
    remittance_id = _linked_beneficiary_and_quote(client, sender_headers, "r8@example.com", "+27000000708")
    _confirmed_remittance(client, sender_headers, admin_headers, remittance_id)
    client.post("/admin/settlement/run", headers=admin_headers)  # succeeds -> completed

    completed = client.get("/admin/settlement?message_status=completed", headers=admin_headers).json()
    message_id = next(m["id"] for m in completed if m["remittance_id"] == remittance_id)

    resp = client.post(f"/admin/settlement/{message_id}/retry", headers=admin_headers)
    assert resp.status_code == 409


def test_non_admin_cannot_access_settlement_endpoints(client, approved_sender):
    headers = approved_sender()
    assert client.get("/admin/settlement", headers=headers).status_code == 403
    assert client.post("/admin/settlement/run", headers=headers).status_code == 403
    assert client.post("/admin/settlement/some-id/retry", headers=headers).status_code == 403


def test_sender_can_view_own_remittance_history(client, approved_sender):
    """FR-28a."""
    headers_a = approved_sender(email="sa@example.com", mobile="+27000000801")
    headers_b = approved_sender(email="sb@example.com", mobile="+27000000802")
    _linked_beneficiary_and_quote(client, headers_a, "ra@example.com", "+27000000811")

    history_a = client.get("/remittances/me", headers=headers_a).json()
    history_b = client.get("/remittances/me", headers=headers_b).json()
    assert len(history_a) == 1
    assert len(history_b) == 0
