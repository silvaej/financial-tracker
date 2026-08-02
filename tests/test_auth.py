from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import auth, crud, models
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


def _create_signup_key(max_uses: int = 1, expires_at: datetime | None = None) -> str:
    db = TestingSessionLocal()
    try:
        key = crud.create_signup_key(db, max_uses=max_uses, expires_at=expires_at)
        return key.key
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


def test_signup_form_redirects_when_already_logged_in(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.get("/signup", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_signup_success_creates_account_logs_in_and_redeems_key(
    real_client: TestClient,
) -> None:
    key = _create_signup_key()

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "newuser@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert real_client.get("/").status_code == 200

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "newuser@example.com")
        assert user is not None
        key_row = db.scalar(select(models.SignupKey).where(models.SignupKey.key == key))
        assert key_row is not None
        assert key_row.use_count == 1
    finally:
        db.close()


def test_signup_rejects_invalid_key(real_client: TestClient) -> None:
    response = real_client.post(
        "/signup",
        data={
            "invite_key": "LEDGER-NOPE-NOPE",
            "email": "newuser@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
    )
    assert response.status_code == 401
    assert "invalid or has expired" in response.text


def test_signup_rejects_expired_key(real_client: TestClient) -> None:
    key = _create_signup_key(expires_at=datetime.now(UTC) - timedelta(days=1))

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "newuser@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
    )
    assert response.status_code == 401
    assert "invalid or has expired" in response.text


def test_signup_rejects_exhausted_key(real_client: TestClient) -> None:
    key = _create_signup_key(max_uses=1)
    real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "first@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
    )

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "second@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
    )
    assert response.status_code == 401
    assert "invalid or has expired" in response.text


def test_signup_rejects_duplicate_email(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    key = _create_signup_key()

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "alice@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        },
    )
    assert response.status_code == 400
    assert "already registered" in response.text


def test_signup_rejects_password_mismatch(real_client: TestClient) -> None:
    key = _create_signup_key()

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "newuser@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "something-else-entirely",
        },
    )
    assert response.status_code == 400
    assert "Passwords" in response.text and "match" in response.text


def test_signup_rejects_short_password(real_client: TestClient) -> None:
    key = _create_signup_key()

    response = real_client.post(
        "/signup",
        data={
            "invite_key": key,
            "email": "newuser@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 400
    assert "at least" in response.text


def test_keep_signed_in_survives_the_default_idle_timeout(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com", "correct-horse")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    real_client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse", "keep_signed_in": "on"},
    )

    past_default_idle = 1000.0 + auth.SESSION_IDLE_TIMEOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: past_default_idle)
    assert real_client.get("/").status_code == 200


def test_keep_signed_in_still_expires_after_its_own_absolute_cap(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com", "correct-horse")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    real_client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse", "keep_signed_in": "on"},
    )

    past_keep_signed_in_cap = 1000.0 + auth.KEEP_SIGNED_IN_ABSOLUTE_TIMEOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: past_keep_signed_in_cap)
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


def _png_bytes() -> bytes:
    # Valid 1x1 transparent PNG.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360606060000000050001a5f6454000000000"
        "49454e44ae426082"
    )


def test_update_profile_persists_all_fields(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/profile",
        data={
            "display_name": "Alice Cooper",
            "currency_code": "USD",
            "timezone": "America/New_York",
            "notify_cash_flow_warnings": "on",
        },
    )
    assert response.status_code == 200
    assert "Profile updated" in response.text

    page = real_client.get("/account")
    assert 'value="Alice Cooper"' in page.text
    assert 'value="USD"' in page.text and "selected" in page.text
    assert "America/New_York" in page.text


def test_update_profile_unchecked_notify_box_is_saved_as_false(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    real_client.post(
        "/account/profile",
        data={"display_name": "", "currency_code": "PHP", "timezone": ""},
    )

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "alice@example.com")
        assert user is not None
        assert user.notify_cash_flow_warnings is False
        assert user.display_name is None
    finally:
        db.close()


def test_update_profile_rejects_invalid_currency(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post("/account/profile", data={"currency_code": "XXX", "timezone": ""})
    assert response.status_code == 400
    assert "valid currency" in response.text


def test_update_profile_rejects_invalid_timezone(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/profile",
        data={"currency_code": "PHP", "timezone": "Not/A_Real_Zone"},
    )
    assert response.status_code == 400
    assert "valid timezone" in response.text


def test_upload_avatar_is_served_and_shown_in_rail(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    before = real_client.get("/account")
    assert 'src="/account/avatar"' not in before.text

    upload = real_client.post(
        "/account/avatar", files={"avatar": ("avatar.png", _png_bytes(), "image/png")}
    )
    assert upload.status_code == 200
    assert 'src="/account/avatar"' in upload.text

    avatar = real_client.get("/account/avatar")
    assert avatar.status_code == 200
    assert avatar.headers["content-type"] == "image/png"
    assert avatar.headers["x-content-type-options"] == "nosniff"
    assert avatar.content == _png_bytes()

    home = real_client.get("/")
    assert 'src="/account/avatar"' in home.text


def test_upload_avatar_rejects_non_image_files(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})

    response = real_client.post(
        "/account/avatar", files={"avatar": ("evil.txt", b"not an image", "text/plain")}
    )
    assert response.status_code == 400


def test_remove_avatar_falls_back_to_icon(real_client: TestClient) -> None:
    _create_user("alice@example.com", "correct-horse")
    real_client.post("/login", data={"email": "alice@example.com", "password": "correct-horse"})
    real_client.post("/account/avatar", files={"avatar": ("avatar.png", _png_bytes(), "image/png")})

    removed = real_client.delete("/account/avatar")
    assert removed.status_code == 200
    assert 'src="/account/avatar"' not in removed.text

    missing = real_client.get("/account/avatar")
    assert missing.status_code == 404

    home = real_client.get("/")
    assert 'src="/account/avatar"' not in home.text
