from decimal import Decimal


def test_request_cash_out_requires_approved_kyc(client, settle_a_remittance):
    """FR-09a: a recipient may hold RLUSD without KYC, but cannot cash out
    without it - the recipient here has a balance but no approved KYC."""
    recipient_headers, _sender_headers, settled = settle_a_remittance()

    resp = client.post(
        "/cash-outs",
        json={"rlusd_amount": settled["rlusd_amount"], "fiat_currency": "USD"},
        headers=recipient_headers,
    )
    assert resp.status_code == 403


def _approve_recipient_kyc(client, admin_headers, recipient_headers, email, mobile):
    client.post(
        "/kyc",
        json={
            "full_name": "Recipient",
            "date_of_birth": "1992-05-01",
            "nationality": "South African",
            "identification_number": "9205015009087",
            "residential_address": "5 Beach Road, Cape Town",
            "mobile_number": mobile,
            "email_address": email,
            "source_of_funds": "Employment",
        },
        headers=recipient_headers,
    )
    application_id = client.get("/kyc/me", headers=recipient_headers).json()["id"]
    client.post(f"/kyc/{application_id}/approve", headers=admin_headers)


def test_request_cash_out_unsupported_currency(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")

    resp = client.post(
        "/cash-outs", json={"rlusd_amount": settled["rlusd_amount"], "fiat_currency": "GBP"}, headers=recipient_headers
    )
    assert resp.status_code == 422


def test_request_cash_out_insufficient_balance(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")

    too_much = Decimal(settled["rlusd_amount"]) + Decimal("1000")
    resp = client.post(
        "/cash-outs", json={"rlusd_amount": str(too_much), "fiat_currency": "USD"}, headers=recipient_headers
    )
    assert resp.status_code == 422
    assert "Insufficient balance" in resp.json()["detail"]


def test_request_cash_out_usd_debits_balance_and_calculates_payout(client, settle_a_remittance, admin_headers):
    """FR-30/FR-31: USD is 1:1, so payout = amount - fee."""
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")

    balance_before = Decimal(client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"])
    cash_out_amount = Decimal("10.000000")

    resp = client.post(
        "/cash-outs", json={"rlusd_amount": str(cash_out_amount), "fiat_currency": "USD"}, headers=recipient_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "requested"
    assert Decimal(body["exchange_rate"]) == Decimal("1")
    expected_fee = (cash_out_amount * Decimal("0.0150")).quantize(Decimal("0.000001"))
    assert Decimal(body["fee_amount_rlusd"]) == expected_fee
    expected_payout = (cash_out_amount - expected_fee).quantize(Decimal("0.01"))
    assert Decimal(body["fiat_payout_amount"]) == expected_payout

    balance_after = Decimal(client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"])
    assert balance_before - balance_after == cash_out_amount


def test_request_cash_out_zar_uses_exchange_rate(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")

    resp = client.post(
        "/cash-outs", json={"rlusd_amount": "10.000000", "fiat_currency": "ZAR"}, headers=recipient_headers
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["exchange_rate"]) == Decimal("18.50")


def test_non_admin_cannot_action_cash_outs(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")
    cash_out_id = client.post(
        "/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers
    ).json()["id"]

    assert client.get("/cash-outs", headers=recipient_headers).status_code == 403
    assert client.post(f"/cash-outs/{cash_out_id}/approve", headers=recipient_headers).status_code == 403


def test_full_admin_lifecycle_approve_then_complete(client, settle_a_remittance, admin_headers):
    """FR-32/FR-35: requested -> approved -> completed."""
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")
    cash_out_id = client.post(
        "/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers
    ).json()["id"]

    approve_resp = client.post(f"/cash-outs/{cash_out_id}/approve", headers=admin_headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    complete_resp = client.post(f"/cash-outs/{cash_out_id}/complete", headers=admin_headers)
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "completed"
    assert complete_resp.json()["completed_at"] is not None


def test_cannot_complete_before_approve(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")
    cash_out_id = client.post(
        "/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers
    ).json()["id"]

    resp = client.post(f"/cash-outs/{cash_out_id}/complete", headers=admin_headers)
    assert resp.status_code == 409


def test_fail_refunds_balance(client, settle_a_remittance, admin_headers):
    """FR-32/FR-35: a failed cash-out returns the reserved RLUSD."""
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")

    balance_before = Decimal(client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"])
    cash_out_id = client.post(
        "/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers
    ).json()["id"]

    fail_resp = client.post(f"/cash-outs/{cash_out_id}/fail", headers=admin_headers)
    assert fail_resp.status_code == 200
    assert fail_resp.json()["status"] == "failed"

    balance_after = Decimal(client.get("/wallet/me", headers=recipient_headers).json()["balance_rlusd"])
    assert balance_after == balance_before


def test_cannot_fail_completed_cash_out(client, settle_a_remittance, admin_headers):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")
    cash_out_id = client.post(
        "/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers
    ).json()["id"]
    client.post(f"/cash-outs/{cash_out_id}/approve", headers=admin_headers)
    client.post(f"/cash-outs/{cash_out_id}/complete", headers=admin_headers)

    resp = client.post(f"/cash-outs/{cash_out_id}/fail", headers=admin_headers)
    assert resp.status_code == 409


def test_recipient_sees_only_own_cash_outs(client, settle_a_remittance, admin_headers, register_and_login):
    recipient_headers, _sender_headers, settled = settle_a_remittance()
    _approve_recipient_kyc(client, admin_headers, recipient_headers, "recipient@example.com", "+27000000777")
    client.post("/cash-outs", json={"rlusd_amount": "5.000000", "fiat_currency": "USD"}, headers=recipient_headers)

    other_headers = register_and_login(email="other@example.com", mobile="+27000000998")
    assert client.get("/cash-outs/me", headers=other_headers).json() == []
    assert len(client.get("/cash-outs/me", headers=recipient_headers).json()) == 1
