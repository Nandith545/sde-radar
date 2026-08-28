"""Security behaviour: login throttling, production config validation,
response headers, and error opacity."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import DEV_JWT_SECRET, validate_for_production
from app.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import login_limiter

CREDENTIALS = {
    "email": "rate@example.com",
    "password": "supersecure123",
    "full_name": "Rate Limited",
    "target_cities": ["Seattle, WA"],
    "target_titles": "Software Engineer",
}


@pytest.fixture(autouse=True)
def _reset_limiter():
    """The limiter is module-level state; without this, tests would leak
    attempt counts into each other and fail depending on ordering."""
    login_limiter.clear()
    yield
    login_limiter.clear()


# ---- The limiter itself -------------------------------------------------


def test_limiter_allows_up_to_the_limit_then_blocks() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)

    assert [limiter.check("k")[0] for _ in range(3)] == [True, True, True]

    allowed, retry_after = limiter.check("k")
    assert allowed is False
    assert retry_after > 0


def test_limiter_tracks_keys_independently() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.check("user-a")[0] is True
    assert limiter.check("user-b")[0] is True  # b is unaffected by a
    assert limiter.check("user-a")[0] is False


def test_limiter_window_expires() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=1)
    assert limiter.check("k")[0] is True
    assert limiter.check("k")[0] is False
    time.sleep(1.1)
    assert limiter.check("k")[0] is True


def test_reset_clears_a_key() -> None:
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("k")
    assert limiter.check("k")[0] is False
    limiter.reset("k")
    assert limiter.check("k")[0] is True


def test_prune_drops_expired_buckets() -> None:
    """Unbounded key growth is a slow memory leak an attacker can drive by
    varying the email on every attempt."""
    limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=1)
    for i in range(50):
        limiter.check(f"key-{i}")
    assert len(limiter._hits) == 50

    time.sleep(1.1)
    limiter.prune()
    assert len(limiter._hits) == 0


# ---- Login endpoint -----------------------------------------------------


def test_repeated_failed_logins_are_throttled(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)

    statuses = [
        client.post(
            "/api/auth/login",
            data={"username": CREDENTIALS["email"], "password": "wrong"},
        ).status_code
        for _ in range(15)
    ]

    assert 429 in statuses, "brute-force attempts were never throttled"
    assert statuses[0] == 401  # the first few are ordinary auth failures


def test_throttled_response_tells_the_client_when_to_retry(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)
    for _ in range(15):
        response = client.post(
            "/api/auth/login", data={"username": CREDENTIALS["email"], "password": "wrong"}
        )
        if response.status_code == 429:
            assert int(response.headers["Retry-After"]) > 0
            return
    pytest.fail("never hit the rate limit")


def test_a_successful_login_clears_the_failure_count(client: TestClient) -> None:
    """Someone who mistypes a few times then gets it right shouldn't stay
    locked out for the rest of the window."""
    client.post("/api/auth/register", json=CREDENTIALS)

    for _ in range(3):
        client.post("/api/auth/login", data={"username": CREDENTIALS["email"], "password": "wrong"})

    ok = client.post(
        "/api/auth/login",
        data={"username": CREDENTIALS["email"], "password": CREDENTIALS["password"]},
    )
    assert ok.status_code == 200

    again = client.post(
        "/api/auth/login",
        data={"username": CREDENTIALS["email"], "password": CREDENTIALS["password"]},
    )
    assert again.status_code == 200


def test_login_for_an_unknown_account_still_returns_401(client: TestClient) -> None:
    response = client.post("/api/auth/login", data={"username": "ghost@example.com", "password": "whatever"})
    assert response.status_code == 401


# ---- Production configuration -------------------------------------------


def test_production_validation_rejects_the_placeholder_secret(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jwt_secret", DEV_JWT_SECRET)
    monkeypatch.setattr("app.config.settings.database_url", "postgresql://u:p@h/db")

    problems = validate_for_production()
    assert any("JWT_SECRET" in p for p in problems)


def test_production_validation_rejects_a_short_secret(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jwt_secret", "tooshort")
    monkeypatch.setattr("app.config.settings.database_url", "postgresql://u:p@h/db")

    assert any("at least" in p for p in validate_for_production())


def test_production_validation_rejects_sqlite(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jwt_secret", "x" * 64)
    monkeypatch.setattr("app.config.settings.database_url", "sqlite:///./dev.db")

    assert any("SQLite" in p for p in validate_for_production())


def test_a_correctly_configured_production_passes(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jwt_secret", "x" * 64)
    monkeypatch.setattr("app.config.settings.database_url", "postgresql://u:p@h/db")

    assert validate_for_production() == []


# ---- Response hardening -------------------------------------------------


@pytest.mark.parametrize(
    "header", ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"]
)
def test_security_headers_are_present(client: TestClient, header: str) -> None:
    assert header in client.get("/api/health").headers


def test_hsts_is_not_sent_outside_production(client: TestClient) -> None:
    """Sending HSTS from a local http dev server pins the browser to https for
    localhost, which is genuinely painful to undo."""
    assert "Strict-Transport-Security" not in client.get("/api/health").headers


def test_auth_errors_do_not_leak_whether_an_account_exists(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)

    wrong_password = client.post(
        "/api/auth/login", data={"username": CREDENTIALS["email"], "password": "wrong"}
    )
    unknown_user = client.post("/api/auth/login", data={"username": "ghost@example.com", "password": "wrong"})

    assert wrong_password.json()["detail"] == unknown_user.json()["detail"]
