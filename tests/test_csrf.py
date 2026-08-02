import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.auth import get_current_user
from app.csrf import csrf_protect
from app.main import app
from tests.conftest import TestingSessionLocal
from tests.conftest import oauth_login as _oauth_login


@pytest.fixture
def real_client() -> Generator[TestClient, None, None]:
    """A client that goes through the real csrf_protect and get_current_user
    dependencies, instead of the global test overrides every other test uses."""
    popped = {
        dep: app.dependency_overrides.pop(dep, None) for dep in (get_current_user, csrf_protect)
    }
    yield TestClient(app)
    for dep, original in popped.items():
        if original is not None:
            app.dependency_overrides[dep] = original


def _login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    db = TestingSessionLocal()
    try:
        crud.create_user(db, "alice@example.com")
    finally:
        db.close()
    # /auth/*/start and /callback are GET (safe methods), so this login path
    # itself never needs a CSRF token -- only the POST assertions below do.
    response = _oauth_login(
        client, monkeypatch, email="alice@example.com", provider_user_id="g-alice"
    )
    assert response.status_code == 303


def _extract_token(html: str) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if match is None:
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_logout_without_csrf_token_is_rejected(real_client: TestClient) -> None:
    response = real_client.post("/logout")

    assert response.status_code == 403


def test_logout_with_valid_csrf_header_succeeds(real_client: TestClient) -> None:
    token = _extract_token(real_client.get("/login").text)

    response = real_client.post("/logout", follow_redirects=False, headers={"X-CSRF-Token": token})

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_post_without_csrf_header_is_rejected(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(real_client, monkeypatch)

    response = real_client.post("/channels", data={"name": "BPI", "color": "#B8122B"})

    assert response.status_code == 403


def test_post_with_wrong_csrf_header_is_rejected(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(real_client, monkeypatch)

    response = real_client.post(
        "/channels",
        data={"name": "BPI", "color": "#B8122B"},
        headers={"X-CSRF-Token": "not-the-real-token"},
    )

    assert response.status_code == 403


def test_post_with_valid_csrf_header_succeeds(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(real_client, monkeypatch)
    token = _extract_token(real_client.get("/").text)

    response = real_client.post(
        "/channels",
        data={"name": "BPI", "color": "#B8122B"},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert "BPI" in response.text
