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


def test_limits_requires_auth(client):
    resp = client.get("/limits/me")
    assert resp.status_code == 401


def test_unverified_user_sees_zero_limits(client, register_and_login):
    """FR-16a, for a user with no approved KYC yet."""
    headers = register_and_login()
    resp = client.get("/limits/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "unverified"
    assert Decimal(body["daily_limit_zar"]) == Decimal("0.00")
    assert Decimal(body["monthly_limit_zar"]) == Decimal("0.00")


def test_verified_user_sees_default_limits_and_zero_usage(client, approved_sender):
    headers = approved_sender()
    resp = client.get("/limits/me", headers=headers)
    body = resp.json()
    assert body["tier"] == "verified"
    assert Decimal(body["daily_limit_zar"]) == Decimal("3000.00")
    assert Decimal(body["monthly_limit_zar"]) == Decimal("25000.00")
    assert Decimal(body["used_today_zar"]) == Decimal("0")
    assert Decimal(body["remaining_today_zar"]) == Decimal("3000.00")


def test_limits_reflect_usage_after_a_quote(client, approved_sender):
    headers = approved_sender()
    beneficiary_id = _add_beneficiary(client, headers)

    client.post("/remittances", json={"beneficiary_id": beneficiary_id, "zar_amount": "1200.00"}, headers=headers)

    resp = client.get("/limits/me", headers=headers)
    body = resp.json()
    assert Decimal(body["used_today_zar"]) == Decimal("1200.00")
    assert Decimal(body["used_this_month_zar"]) == Decimal("1200.00")
    assert Decimal(body["remaining_today_zar"]) == Decimal("1800.00")
    assert Decimal(body["remaining_this_month_zar"]) == Decimal("23800.00")
