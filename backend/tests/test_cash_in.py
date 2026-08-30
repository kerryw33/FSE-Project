def _add_beneficiary(client, headers, email="ben@example.com"):
    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Ben Recipient",
            "email_address": email,
            "country": "South Africa",
            "payout_currency": "USD",
            "relationship_to_sender": "Friend",
        },
        headers=headers,
    )
    return resp.json()["id"]


def _create_quote(client, headers, zar_amount="1000.00"):
    beneficiary_id = _add_beneficiary(client, headers)
    resp = client.post("/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": zar_amount}, headers=headers)
    return resp.json()["id"]


def test_initiate_cash_in_requires_ownership(client, approved_sender):
    headers_a = approved_sender(email="a@example.com", mobile="+27000000001")
    headers_b = approved_sender(email="b@example.com", mobile="+27000000002")
    remittance_id = _create_quote(client, headers_a)

    resp = client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "bank_transfer"}, headers=headers_b)
    assert resp.status_code == 404


def test_initiate_cash_in_success(client, approved_sender):
    """FR-18: sender initiates a simulated ZAR payment via one method."""
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)

    resp = client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "agent_cash"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cash_in_pending"
    assert body["cash_in_method"] == "agent_cash"
    assert body["cash_in_initiated_at"] is not None


def test_initiate_cash_in_rejects_invalid_method(client, approved_sender):
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)

    resp = client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "crypto"}, headers=headers)
    assert resp.status_code == 422


def test_cannot_initiate_cash_in_twice(client, approved_sender):
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)
    client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "card"}, headers=headers)

    resp = client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "card"}, headers=headers)
    assert resp.status_code == 409


def test_confirm_cash_in_requires_admin(client, approved_sender):
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)
    client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "card"}, headers=headers)

    resp = client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=headers)
    assert resp.status_code == 403


def test_cannot_confirm_cash_in_before_initiation(client, approved_sender, admin_headers):
    """FR-20: nothing to confirm (and nothing for settlement to act on)
    while still in the 'quoted' state."""
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)

    resp = client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)
    assert resp.status_code == 409


def test_confirm_cash_in_success(client, approved_sender, admin_headers):
    """FR-19: admin confirms a simulated ZAR cash-in has been received."""
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)
    client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "bank_transfer"}, headers=headers)

    resp = client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cash_in_confirmed"
    assert body["cash_in_confirmed_at"] is not None


def test_cannot_confirm_cash_in_twice(client, approved_sender, admin_headers):
    headers = approved_sender()
    remittance_id = _create_quote(client, headers)
    client.post(f"/remittances/{remittance_id}/cash-in", json={"method": "bank_transfer"}, headers=headers)
    client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)

    resp = client.post(f"/remittances/{remittance_id}/confirm-cash-in", headers=admin_headers)
    assert resp.status_code == 409


def test_admin_can_list_remittances_pending_cash_in(client, approved_sender, admin_headers):
    """FR-34: admin interface for finding cash-ins to confirm."""
    headers = approved_sender()
    quoted_only_id = _create_quote(client, headers, zar_amount="500.00")
    pending_id = _create_quote(client, headers, zar_amount="600.00")
    client.post(f"/remittances/{pending_id}/cash-in", json={"method": "card"}, headers=headers)

    resp = client.get("/remittances?remittance_status=cash_in_pending", headers=admin_headers)
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert pending_id in ids
    assert quoted_only_id not in ids


def test_non_admin_cannot_list_remittances(client, approved_sender):
    headers = approved_sender()
    resp = client.get("/remittances", headers=headers)
    assert resp.status_code == 403
