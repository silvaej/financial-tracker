from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.auth import get_current_user, hash_password
from app.main import app
from tests.conftest import TestingSessionLocal


@pytest.fixture
def real_client() -> Generator[TestClient, None, None]:
    """A client that goes through the real get_current_user dependency (session
    cookie based), instead of the global test override every other test uses."""
    original = app.dependency_overrides.pop(get_current_user, None)
    yield TestClient(app)
    if original is not None:
        app.dependency_overrides[get_current_user] = original


def _create_user(email: str, password: str) -> int:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, email, hash_password(password))
        return user.id
    finally:
        db.close()


def test_login_success_sets_session_and_redirects(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")

    response = real_client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    home = real_client.get("/")
    assert home.status_code == 200


def test_login_failure_shows_error(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")

    response = real_client.post(
        "/login", data={"email": "alice@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.text


def test_logout_clears_session(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    real_client.post("/logout")

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_plain_request_redirects_to_login(real_client: TestClient) -> None:
    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_htmx_request_gets_hx_redirect(real_client: TestClient) -> None:
    response = real_client.get("/goals", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/login"


def test_cross_user_data_isolation(real_client: TestClient) -> None:
    _create_user("alice@example.com", "alice-pass")
    _create_user("bob@example.com", "bob-pass")

    real_client.post("/login", data={"email": "alice@example.com", "password": "alice-pass"})
    create = real_client.post("/channels", data={"name": "Alice Bank", "color": "#8a8a8a"})
    assert "Alice Bank" in create.text

    real_client.post("/logout")
    real_client.post("/login", data={"email": "bob@example.com", "password": "bob-pass"})

    expenses_page = real_client.get("/expenses")
    assert "Alice Bank" not in expenses_page.text
