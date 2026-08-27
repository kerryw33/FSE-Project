def test_get_profile(client, register_and_login):
    headers = register_and_login()
    resp = client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "sender@example.com"


def test_update_profile_full_name(client, register_and_login):
    headers = register_and_login()
    resp = client.patch("/users/me", json={"full_name": "New Name"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "New Name"


def test_update_profile_to_taken_email_rejected(client, register_and_login):
    headers = register_and_login()
    client.post(
        "/auth/register",
        json={
            "full_name": "Other",
            "email": "taken@example.com",
            "mobile_number": "+27000000002",
            "password": "StrongPass123",
        },
    )
    resp = client.patch("/users/me", json={"email": "taken@example.com"}, headers=headers)
    assert resp.status_code == 409


def test_update_profile_email_and_mobile(client, register_and_login):
    headers = register_and_login()
    resp = client.patch(
        "/users/me",
        json={"email": "updated@example.com", "mobile_number": "+27000000055"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "updated@example.com"
    assert body["mobile_number"] == "+27000000055"
