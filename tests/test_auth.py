from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import auth, crud
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


def test_login_locks_out_after_max_failed_attempts(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")

    for _ in range(crud.LOGIN_MAX_ATTEMPTS):
        response = real_client.post(
            "/login", data={"email": "alice@example.com", "password": "wrong-password"}
        )
        assert response.status_code == 401

    locked_response = real_client.post(
        "/login", data={"email": "alice@example.com", "password": "correct-horse"}
    )
    assert locked_response.status_code == 429
    assert "Too many failed attempts" in locked_response.text


def test_login_success_resets_failed_attempts(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")

    for _ in range(crud.LOGIN_MAX_ATTEMPTS - 1):
        real_client.post(
            "/login", data={"email": "alice@example.com", "password": "wrong-password"}
        )

    success = real_client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse"},
        follow_redirects=False,
    )
    assert success.status_code == 303

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "alice@example.com")
        assert user is not None
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
    finally:
        db.close()


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


def test_idle_session_is_rejected(real_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    future = 1000.0 + auth.SESSION_IDLE_TIMEOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: future)

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_activity_slides_the_idle_window(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com", "correct-horse")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    just_under_idle_timeout = 1000.0 + auth.SESSION_IDLE_TIMEOUT_SECONDS - 1
    monkeypatch.setattr(auth.time, "time", lambda: just_under_idle_timeout)
    assert real_client.get("/").status_code == 200

    # Idle window slid forward on that last request, so another near-timeout
    # gap from *there* should still be authenticated.
    monkeypatch.setattr(
        auth.time, "time", lambda: just_under_idle_timeout + auth.SESSION_IDLE_TIMEOUT_SECONDS - 1
    )
    assert real_client.get("/").status_code == 200


def test_absolute_session_lifetime_is_enforced_despite_activity(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com", "correct-horse")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    # Stay active often enough to never hit the idle timeout, but long enough
    # to blow past the absolute session lifetime.
    step = auth.SESSION_IDLE_TIMEOUT_SECONDS - 1
    now = 1000.0
    deadline = 1000.0 + auth.SESSION_ABSOLUTE_TIMEOUT_SECONDS + step
    response = None
    while now < deadline:
        now += step
        monkeypatch.setattr(auth.time, "time", lambda now=now: now)
        response = real_client.get("/", follow_redirects=False)

    assert response is not None
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


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


def test_account_page_requires_login(real_client: TestClient) -> None:
    response = real_client.get("/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_change_password_success_and_relogin(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/password",
        data={
            "current_password": "correct-horse",
            "new_password": "new-correct-horse",
            "confirm_password": "new-correct-horse",
        },
    )
    assert response.status_code == 200
    assert "Password updated" in response.text

    real_client.post("/logout")
    relogin = real_client.post(
        "/login",
        data={"email": "alice@example.com", "password": "new-correct-horse"},
        follow_redirects=False,
    )
    assert relogin.status_code == 303


def test_change_password_rejects_wrong_current_password(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/password",
        data={
            "current_password": "wrong-password",
            "new_password": "new-correct-horse",
            "confirm_password": "new-correct-horse",
        },
    )
    assert response.status_code == 401
    assert "Current password is incorrect" in response.text


def test_change_password_rejects_mismatched_confirmation(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/password",
        data={
            "current_password": "correct-horse",
            "new_password": "new-correct-horse",
            "confirm_password": "something-else",
        },
    )
    assert response.status_code == 400
    assert "New passwords" in response.text and "match" in response.text


def test_change_password_rejects_short_password(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/password",
        data={
            "current_password": "correct-horse",
            "new_password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 400
    assert "at least" in response.text
