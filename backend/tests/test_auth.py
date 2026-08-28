"""Authentication: registration, login, token handling, profile updates."""

import pytest
from fastapi.testclient import TestClient

VALID = {
    "email": "new@example.com",
    "password": "supersecure123",
    "full_name": "New User",
    "target_city": "Seattle, WA",
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
        json={"target_city": "Bellevue, WA", "target_titles": "Staff Engineer"},
        headers=registered_user["headers"],
    )
    assert response.status_code == 200
    assert response.json()["target_city"] == "Bellevue, WA"
    assert response.json()["target_titles"] == "Staff Engineer"
    # Unspecified fields are left alone rather than blanked.
    assert response.json()["full_name"] == registered_user["full_name"]
