from decimal import Decimal


def test_wallet_requires_auth(client):
    resp = client.get("/wallet/me")
    assert resp.status_code == 401


def test_wallet_starts_at_zero_balance(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/wallet/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["balance_rlusd"]) == Decimal("0")
    assert body["xrpl_address"] is None
    assert body["incoming_transfers"] == []
    assert body["cash_out_transactions"] == []


def test_wallet_shows_settled_incoming_transfer(client, settle_a_remittance):
    """FR-27/FR-28: balance, XRPL address, and incoming transfer with
    status/date/tx hash all populated once settlement succeeds."""
    recipient_headers, _sender_headers, settled = settle_a_remittance()

    wallet = client.get("/wallet/me", headers=recipient_headers).json()
    assert Decimal(wallet["balance_rlusd"]) == Decimal(settled["rlusd_amount"])
    assert wallet["xrpl_address"] is not None

    assert len(wallet["incoming_transfers"]) == 1
    transfer = wallet["incoming_transfers"][0]
    assert transfer["remittance_id"] == settled["id"]
    assert transfer["status"] == "settled"
    assert transfer["xrpl_tx_hash"] == settled["xrpl_settlement_tx_hash"]


def test_wallet_hides_other_recipients_transfers(client, settle_a_remittance, register_and_login):
    recipient_headers, _sender_headers, _settled = settle_a_remittance()
    other_headers = register_and_login(email="other@example.com", mobile="+27000000999")

    other_wallet = client.get("/wallet/me", headers=other_headers).json()
    assert other_wallet["incoming_transfers"] == []
    assert Decimal(other_wallet["balance_rlusd"]) == Decimal("0")
