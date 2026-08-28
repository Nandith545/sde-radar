"""The SPA catch-all's path safety.

The catch-all served any file the URL pointed at, including via
"%2e%2e/%2e%2e/.env" -- source, config, and the JWT secret were all readable.
These tests build a static root with a secret file sitting just outside it and
assert the traversal payloads that actually worked now resolve to nothing.

The logic is tested through `safe_static_file` directly rather than over HTTP,
because the catch-all route only mounts when a real ``static`` dir exists, and
the backend test job builds no frontend.
"""

from pathlib import Path

import pytest

from app.main import safe_static_file


@pytest.fixture()
def static_root(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html>")
    (root / "assets" / "app.js").write_text("console.log(1)")
    # A secret sitting one level up, exactly like backend/.env relative to
    # backend/static in the real layout.
    (tmp_path / ".env").write_text("JWT_SECRET=super-secret")
    return root


def test_a_real_bundled_file_is_served(static_root: Path) -> None:
    served = safe_static_file(static_root, "assets/app.js")
    assert served is not None and served.name == "app.js"


def test_index_is_served_by_name(static_root: Path) -> None:
    assert safe_static_file(static_root, "index.html") is not None


def test_a_client_route_has_no_file(static_root: Path) -> None:
    """ "/settings" and friends correctly resolve to nothing so the caller can
    fall through to index.html."""
    assert safe_static_file(static_root, "settings") is None


def test_an_empty_path_returns_none(static_root: Path) -> None:
    assert safe_static_file(static_root, "") is None


@pytest.mark.parametrize(
    "payload",
    [
        # Starlette percent-decodes before the handler, so by the time
        # safe_static_file runs these are literal "../" sequences.
        "../.env",
        "../../.env",
        "../../../../../.env",
        "assets/../../.env",
        "./../.env",
    ],
)
def test_traversal_to_the_secret_is_refused(static_root: Path, payload: str) -> None:
    """The exact class of payload that read backend/.env in production's app.

    A regression here would re-expose the JWT secret, so this is the test that
    matters most in the file.
    """
    assert safe_static_file(static_root, payload) is None


def test_an_absolute_path_escape_is_refused(static_root: Path, tmp_path: Path) -> None:
    assert safe_static_file(static_root, str(tmp_path / ".env")) is None
