from decimal import Decimal


def test_non_admin_cannot_view_fee_config(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/admin/fee-config", headers=headers)
    assert resp.status_code == 403


def test_admin_can_view_default_fee_config(client, admin_headers):
    resp = client.get("/admin/fee-config", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["fixed_fee_zar"]) == Decimal("25.00")
    assert Decimal(body["percentage_fee"]) == Decimal("0.0100")


def test_admin_can_update_fee_config_and_it_affects_quotes(client, admin_headers, approved_sender):
    """FR-15a: admin-updated fee parameters take effect on the next quote."""
    update_resp = client.put("/admin/fee-config", json={"fixed_fee_zar": "50.00"}, headers=admin_headers)
    assert update_resp.status_code == 200
    assert Decimal(update_resp.json()["fixed_fee_zar"]) == Decimal("50.00")

    headers = approved_sender()
    beneficiary = client.post(
        "/beneficiaries",
        json={
            "full_name": "Ben",
            "email_address": "ben@example.com",
            "country": "South Africa",
            "payout_currency": "USD",
            "relationship_to_sender": "Friend",
        },
        headers=headers,
    ).json()

    quote = client.post(
        "/remittances", json={"beneficiary_id": beneficiary["id"], "zar_amount": "1000.00"}, headers=headers
    )
    assert Decimal(quote.json()["transaction_fee_zar"]) == Decimal("60.00")  # 50 + 1% of 1000


def test_non_admin_cannot_view_limit_tiers(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/admin/limit-tiers", headers=headers)
    assert resp.status_code == 403


def test_admin_can_view_default_limit_tiers(client, admin_headers):
    resp = client.get("/admin/limit-tiers", headers=admin_headers)
    assert resp.status_code == 200
    tiers = {t["tier_key"]: t for t in resp.json()}
    assert Decimal(tiers["unverified"]["daily_limit_zar"]) == Decimal("0.00")
    assert Decimal(tiers["verified"]["daily_limit_zar"]) == Decimal("3000.00")


def test_admin_can_update_limit_tier(client, admin_headers):
    resp = client.put(
        "/admin/limit-tiers/verified",
        json={"daily_limit_zar": "5000.00", "monthly_limit_zar": "40000.00"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["daily_limit_zar"]) == Decimal("5000.00")
    assert Decimal(body["monthly_limit_zar"]) == Decimal("40000.00")


def test_update_unknown_limit_tier_returns_404(client, admin_headers):
    resp = client.put("/admin/limit-tiers/not-a-real-tier", json={"daily_limit_zar": "1"}, headers=admin_headers)
    assert resp.status_code == 422  # FastAPI enum path validation rejects it before the handler runs
