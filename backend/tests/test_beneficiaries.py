def test_add_beneficiary_requires_approved_kyc(client, register_and_login):
    """FR-10: only an approved sender may add a beneficiary."""
    headers = register_and_login()
    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Bob Recipient",
            "email_address": "bob@example.com",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Brother",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_add_beneficiary_requires_mobile_or_email(client, approved_sender):
    """FR-11: at least a mobile number or an email address is required."""
    headers = approved_sender()
    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Bob Recipient",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Brother",
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_add_beneficiary_with_only_email_succeeds(client, approved_sender):
    headers = approved_sender()
    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Bob Recipient",
            "email_address": "bob@example.com",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Brother",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Bob Recipient"
    assert body["linked_user_id"] is None
    assert body["wallet_provisioned"] is False


def test_add_beneficiary_auto_links_to_existing_account(client, approved_sender, register_and_login):
    """FR-12a: matches against an already-registered account by email.
    FR-12b: a wallet is provisioned once linked."""
    sender_headers = approved_sender()
    register_and_login(email="recipient@example.com", mobile="+27000000777", password="RecipientPass123")

    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Existing Recipient",
            "email_address": "recipient@example.com",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Friend",
        },
        headers=sender_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["linked_user_id"] is not None
    assert body["wallet_provisioned"] is True


def test_add_beneficiary_auto_links_by_mobile_number(client, approved_sender, register_and_login):
    sender_headers = approved_sender()
    register_and_login(email="recipient2@example.com", mobile="+27000000888", password="RecipientPass123")

    resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Existing Recipient",
            "mobile_number": "+27000000888",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Friend",
        },
        headers=sender_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["linked_user_id"] is not None


def test_unlinked_beneficiary_links_retroactively_on_registration(client, approved_sender, register_and_login):
    """FR-12c: a beneficiary added before the matching account exists stays
    unlinked, then links automatically once that account registers."""
    sender_headers = approved_sender()

    add_resp = client.post(
        "/beneficiaries",
        json={
            "full_name": "Future Recipient",
            "email_address": "future@example.com",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Cousin",
        },
        headers=sender_headers,
    )
    assert add_resp.json()["linked_user_id"] is None

    register_and_login(email="future@example.com", mobile="+27000000555", password="FuturePass123")

    list_resp = client.get("/beneficiaries", headers=sender_headers)
    beneficiary = list_resp.json()[0]
    assert beneficiary["linked_user_id"] is not None
    assert beneficiary["wallet_provisioned"] is True


def test_list_beneficiaries_returns_only_own(client, approved_sender):
    """FR-12: a sender only sees the beneficiaries they added."""
    headers_a = approved_sender(email="sender-a@example.com", mobile="+27000000011")
    headers_b = approved_sender(email="sender-b@example.com", mobile="+27000000022")

    client.post(
        "/beneficiaries",
        json={
            "full_name": "A's Beneficiary",
            "email_address": "a-ben@example.com",
            "country": "South Africa",
            "payout_currency": "ZAR",
            "relationship_to_sender": "Friend",
        },
        headers=headers_a,
    )

    list_a = client.get("/beneficiaries", headers=headers_a)
    list_b = client.get("/beneficiaries", headers=headers_b)

    assert len(list_a.json()) == 1
    assert len(list_b.json()) == 0


def test_list_beneficiaries_requires_auth(client):
    resp = client.get("/beneficiaries")
    assert resp.status_code == 401
