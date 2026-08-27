def register(client, email="a@example.com", mobile="+27000000001", password="StrongPass123"):
    return client.post(
        "/auth/register",
        json={"full_name": "Alice Sender", "email": email, "mobile_number": mobile, "password": password},
    )


def test_register_creates_customer(client):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@example.com"
    assert body["role"] == "customer"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_email_rejected(client):
    register(client)
    resp = register(client, mobile="+27000000002")
    assert resp.status_code == 409


def test_register_duplicate_mobile_rejected(client):
    register(client)
    resp = register(client, email="different@example.com")
    assert resp.status_code == 409


def test_login_succeeds_with_correct_credentials(client):
    register(client)
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "StrongPass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "a@example.com"


def test_login_fails_with_wrong_password(client):
    register(client)
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "WrongPass"})
    assert resp.status_code == 401


def test_login_fails_for_unknown_email(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert resp.status_code == 401


def test_logout_revokes_session(client):
    register(client)
    login_resp = client.post("/auth/login", json={"email": "a@example.com", "password": "StrongPass123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/users/me", headers=headers).status_code == 200

    logout_resp = client.post("/auth/logout", headers=headers)
    assert logout_resp.status_code == 204

    after_logout = client.get("/users/me", headers=headers)
    assert after_logout.status_code == 401


def test_protected_route_requires_auth(client):
    resp = client.get("/users/me")
    assert resp.status_code == 401
