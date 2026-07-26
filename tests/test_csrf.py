import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.auth import get_current_user, hash_password
from app.csrf import csrf_protect
from app.main import app
from tests.conftest import TestingSessionLocal


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


def _login(client: TestClient) -> None:
    db = TestingSessionLocal()
    try:
        crud.create_user(db, "alice@example.com", hash_password("correct-horse"))
    finally:
        db.close()
    token = _extract_token(client.get("/login").text)
    response = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _extract_token(html: str) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if match is None:
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_login_without_csrf_token_is_rejected(real_client: TestClient) -> None:
    db = TestingSessionLocal()
    try:
        crud.create_user(db, "alice@example.com", hash_password("correct-horse"))
    finally:
        db.close()
    real_client.get("/login")

    response = real_client.post(
        "/login", data={"email": "alice@example.com", "password": "correct-horse"}
    )

    assert response.status_code == 403


def test_login_with_valid_csrf_token_succeeds(real_client: TestClient) -> None:
    _login(real_client)

    home = real_client.get("/")
    assert home.status_code == 200


def test_post_without_csrf_header_is_rejected(real_client: TestClient) -> None:
    _login(real_client)

    response = real_client.post("/channels", data={"name": "BPI", "color": "#B8122B"})

    assert response.status_code == 403


def test_post_with_wrong_csrf_header_is_rejected(real_client: TestClient) -> None:
    _login(real_client)

    response = real_client.post(
        "/channels",
        data={"name": "BPI", "color": "#B8122B"},
        headers={"X-CSRF-Token": "not-the-real-token"},
    )

    assert response.status_code == 403


def test_post_with_valid_csrf_header_succeeds(real_client: TestClient) -> None:
    _login(real_client)
    token = _extract_token(real_client.get("/").text)

    response = real_client.post(
        "/channels",
        data={"name": "BPI", "color": "#B8122B"},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert "BPI" in response.text
