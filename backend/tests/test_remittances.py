from decimal import Decimal


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


def test_create_quote_requires_approved_kyc(client, register_and_login):
    headers = register_and_login()
    resp = client.post("/remittances", json={"beneficiary_id": "whatever", "zar_amount": "100.00"}, headers=headers)
    assert resp.status_code == 403


def test_create_quote_for_nonexistent_beneficiary(client, approved_sender):
    headers = approved_sender()
    resp = client.post(
        "/remittances", json={"beneficiary_id": "does-not-exist", "zar_amount": "100.00"}, headers=headers
    )
    assert resp.status_code == 404


def test_create_quote_rejects_other_senders_beneficiary(client, approved_sender):
    headers_a = approved_sender(email="a@example.com", mobile="+27000000001")
    headers_b = approved_sender(email="b@example.com", mobile="+27000000002")
    beneficiary_id = _add_beneficiary(client, headers_a)

    resp = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "100.00"}, headers=headers_b
    )
    assert resp.status_code == 404


def test_create_quote_returns_full_fee_breakdown(client, approved_sender):
    """FR-14: default fee config is fixed=25.00 ZAR, pct=1%, fx_margin=2%,
    cash_out_fee=1.5%. Default USD/ZAR rate is 18.50. Verify the maths for
    a known ZAR 1000 send."""
    headers = approved_sender()
    beneficiary_id = _add_beneficiary(client, headers)

    resp = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "1000.00"}, headers=headers
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "quoted"
    assert Decimal(body["transaction_fee_zar"]) == Decimal("35.00")  # 25 + 1% of 1000
    assert Decimal(body["exchange_rate"]) == Decimal("18.870000")  # 18.50 * 1.02
    expected_rlusd = (Decimal("1000.00") - Decimal("35.00")) / Decimal("18.870000")
    assert Decimal(body["rlusd_amount"]) == expected_rlusd.quantize(Decimal("0.000001"))
    assert Decimal(body["fx_margin_percentage"]) == Decimal("0.0200")
    assert Decimal(body["cash_out_fee_percentage"]) == Decimal("0.0150")


def test_create_quote_rejected_over_daily_limit(client, approved_sender):
    """FR-16/FR-17: default verified tier is ZAR 3000 daily / 25000 monthly."""
    headers = approved_sender()
    beneficiary_id = _add_beneficiary(client, headers)

    first = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "2500.00"}, headers=headers
    )
    assert first.status_code == 201

    second = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "600.00"}, headers=headers
    )
    assert second.status_code == 422
    assert "daily limit" in second.json()["detail"]


def test_create_quote_rejected_over_monthly_limit(client, approved_sender, admin_headers):
    """Raise the daily cap via the admin endpoint so the monthly cap is the
    one being exercised in isolation (FR-16b feeding into FR-17)."""
    headers = approved_sender()
    beneficiary_id = _add_beneficiary(client, headers)

    client.put("/admin/limit-tiers/verified", json={"daily_limit_zar": "100000"}, headers=admin_headers)

    first = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "24000.00"}, headers=headers
    )
    assert first.status_code == 201

    second = client.post(
        "/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "2000.00"}, headers=headers
    )
    assert second.status_code == 422
    assert "monthly limit" in second.json()["detail"]
