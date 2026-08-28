"""Authentication: registration, login, token handling, profile updates."""

import pytest
from fastapi.testclient import TestClient

VALID = {
    "email": "new@example.com",
    "password": "supersecure123",
    "full_name": "New User",
    "target_cities": ["Seattle, WA"],
    "target_titles": "Software Engineer",
}


def test_register_returns_a_usable_token(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=VALID)
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert token

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == VALID["email"]
    assert me.json()["has_resume"] is False


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    assert client.post("/api/auth/register", json=VALID).status_code == 200
    duplicate = client.post("/api/auth/register", json=VALID)
    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password", "short"),  # below the 8-char minimum
        ("email", "not-an-email"),  # fails EmailStr validation
        ("full_name", ""),  # min_length=1
    ],
)
def test_register_rejects_invalid_input(client: TestClient, field: str, value: str) -> None:
    payload = {**VALID, field: value}
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_password_is_not_stored_in_plaintext(client: TestClient, db) -> None:
    from app import models

    client.post("/api/auth/register", json=VALID)
    user = db.query(models.User).filter(models.User.email == VALID["email"]).first()
    assert user is not None
    assert user.hashed_password != VALID["password"]
    assert user.hashed_password.startswith("$2")  # bcrypt marker


def test_login_succeeds_with_correct_credentials(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID)
    response = client.post(
        "/api/auth/login",
        data={"username": VALID["email"], "password": VALID["password"]},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_fails_with_wrong_password(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID)
    response = client.post(
        "/api/auth/login",
        data={"username": VALID["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_error_does_not_reveal_whether_the_account_exists(client: TestClient) -> None:
    """Distinct messages for 'no such user' vs 'wrong password' would let an
    attacker enumerate registered email addresses."""
    client.post("/api/auth/register", json=VALID)

    wrong_password = client.post(
        "/api/auth/login", data={"username": VALID["email"], "password": "wrongpassword"}
    )
    no_such_user = client.post(
        "/api/auth/login", data={"username": "nobody@example.com", "password": "wrongpassword"}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]


@pytest.mark.parametrize("header", [None, "Bearer garbage", "Bearer ", "NotBearer xyz"])
def test_protected_routes_reject_bad_tokens(client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_update_profile(client: TestClient, registered_user: dict) -> None:
    response = client.patch(
        "/api/auth/me",
        json={"target_cities": ["Bellevue, WA"], "target_titles": "Staff Engineer"},
        headers=registered_user["headers"],
    )
    assert response.status_code == 200
    assert response.json()["target_cities"] == ["Bellevue, WA"]
    assert response.json()["target_titles"] == "Staff Engineer"
    # Unspecified fields are left alone rather than blanked.
    assert response.json()["full_name"] == registered_user["full_name"]


# ---- Account changes ---------------------------------------------------


def _register(client: TestClient) -> str:
    return client.post("/api/auth/register", json=VALID).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_existing_token_still_works_after_a_password_change(client: TestClient) -> None:
    """No new token is issued, because none is needed: the JWT subject is the
    email and nothing in it derives from the password."""
    token = _register(client)
    client.post(
        "/api/auth/password",
        json={"current_password": VALID["password"], "new_password": "brand-new-secret-1"},
        headers=_auth(token),
    )
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


def test_password_change_lets_you_log_in_with_the_new_password(client: TestClient) -> None:
    token = _register(client)

    changed = client.post(
        "/api/auth/password",
        json={"current_password": VALID["password"], "new_password": "brand-new-secret-1"},
        headers=_auth(token),
    )
    assert changed.status_code == 204

    old = client.post("/api/auth/login", data={"username": VALID["email"], "password": VALID["password"]})
    assert old.status_code == 401
    new = client.post("/api/auth/login", data={"username": VALID["email"], "password": "brand-new-secret-1"})
    assert new.status_code == 200


def test_password_change_requires_the_current_password(client: TestClient) -> None:
    """A token left open on a shared machine must not be enough on its own."""
    token = _register(client)

    response = client.post(
        "/api/auth/password",
        json={"current_password": "not-the-password", "new_password": "brand-new-secret-1"},
        headers=_auth(token),
    )
    assert response.status_code == 400
    # The original password must still work.
    assert (
        client.post(
            "/api/auth/login", data={"username": VALID["email"], "password": VALID["password"]}
        ).status_code
        == 200
    )


def test_password_change_rejects_a_too_short_password(client: TestClient) -> None:
    token = _register(client)
    response = client.post(
        "/api/auth/password",
        json={"current_password": VALID["password"], "new_password": "short"},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_email_change_returns_a_token_that_still_works(client: TestClient) -> None:
    """The JWT subject is the email, so the old token stops resolving the
    moment this commits -- without a replacement the user is signed out."""
    token = _register(client)

    response = client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "current_password": VALID["password"]},
        headers=_auth(token),
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]

    me = client.get("/api/auth/me", headers=_auth(new_token))
    assert me.status_code == 200
    assert me.json()["email"] == "moved@example.com"


def test_email_change_requires_the_password(client: TestClient) -> None:
    token = _register(client)
    response = client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "current_password": "wrong"},
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_email_change_rejects_an_address_already_in_use(client: TestClient) -> None:
    client.post("/api/auth/register", json={**VALID, "email": "taken@example.com"})
    token = _register(client)

    response = client.post(
        "/api/auth/email",
        json={"new_email": "taken@example.com", "current_password": VALID["password"]},
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_address_and_phone_round_trip(client: TestClient) -> None:
    token = _register(client)

    client.patch(
        "/api/auth/me",
        json={"address": "1 Example Way, Seattle, WA 98101", "phone": "+1 555 0100"},
        headers=_auth(token),
    )
    me = client.get("/api/auth/me", headers=_auth(token)).json()
    assert me["address"] == "1 Example Way, Seattle, WA 98101"
    assert me["phone"] == "+1 555 0100"


def test_multiple_target_cities_round_trip(client: TestClient, registered_user: dict) -> None:
    response = client.patch(
        "/api/auth/me",
        json={"target_cities": ["Seattle, WA", "Bellevue, WA", "Redmond, WA"]},
        headers=registered_user["headers"],
    )
    assert response.status_code == 200
    assert response.json()["target_cities"] == ["Seattle, WA", "Bellevue, WA", "Redmond, WA"]


def test_target_cities_are_trimmed_and_deduplicated(client: TestClient, registered_user: dict) -> None:
    """Applied server-side, so anything hitting the API directly gets the same
    treatment as the form does."""
    response = client.patch(
        "/api/auth/me",
        json={"target_cities": ["  Seattle, WA  ", "seattle, wa", "", "   ", "Austin, TX"]},
        headers=registered_user["headers"],
    )
    assert response.json()["target_cities"] == ["Seattle, WA", "Austin, TX"]


def test_clearing_target_cities_means_anywhere(client: TestClient, registered_user: dict) -> None:
    response = client.patch("/api/auth/me", json={"target_cities": []}, headers=registered_user["headers"])
    assert response.json()["target_cities"] == []
