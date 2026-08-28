"""The SPA catch-all's path safety.

The catch-all once served any file the URL pointed at, including via
"%2e%2e/%2e%2e/.env" -- source, config, and the JWT secret were all readable.
It no longer builds a filesystem path from the URL at all: root files are
enumerated once into an allowlist and the request name is looked up in it, so
there is nothing for a traversal payload to resolve through.

These tests exercise `static_root_allowlist` -- the catch-all route only
mounts when a real ``static`` dir exists, which the backend test job does not
build -- with a secret file planted just outside the root.
"""

from pathlib import Path

import pytest

from app.main import static_root_allowlist


@pytest.fixture()
def static_root(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html>")
    (root / "favicon.ico").write_text("icon")
    (root / "assets" / "app.js").write_text("console.log(1)")
    # A secret one level up, exactly like backend/.env relative to
    # backend/static in the real layout.
    (tmp_path / ".env").write_text("JWT_SECRET=super-secret")
    return root


def test_root_files_are_in_the_allowlist(static_root: Path) -> None:
    allow = static_root_allowlist(static_root)
    assert "index.html" in allow
    assert "favicon.ico" in allow


def test_the_assets_directory_is_not_a_root_file(static_root: Path) -> None:
    """Hashed assets are served by the /assets mount, not this allowlist."""
    assert "assets" not in static_root_allowlist(static_root)


def test_nothing_outside_the_root_is_reachable(static_root: Path) -> None:
    """The allowlist is keyed by bare filename, so no request name can name a
    file that isn't directly in the bundle root."""
    allow = static_root_allowlist(static_root)
    values = {p.resolve() for p in allow.values()}
    assert (static_root.parent / ".env").resolve() not in values
    for served in values:
        assert served.parent.resolve() == static_root.resolve()


@pytest.mark.parametrize(
    "payload",
    [
        # The exact class of value that read backend/.env before the rewrite.
        # Starlette percent-decodes before the handler, so by the time it does
        # the dict lookup these are literal strings -- and none is a key.
        "../.env",
        "../../.env",
        "../../../../../.env",
        "assets/../../.env",
        ".env",
        "settings",  # a real client route: also a miss, also -> index.html
    ],
)
def test_a_traversal_or_client_route_is_not_in_the_allowlist(static_root: Path, payload: str) -> None:
    assert payload not in static_root_allowlist(static_root)
