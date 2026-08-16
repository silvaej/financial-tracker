from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote_plus

import httpx
import pytest
from authlib.integrations.base_client import OAuthError
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from app import auth, crud, models
from app import oauth as oauth_module
from app.auth import get_current_user
from app.main import app
from tests.conftest import TestingSessionLocal
from tests.conftest import oauth_login as _oauth_login


@pytest.fixture
def real_client() -> Generator[TestClient, None, None]:
    """A client that goes through the real get_current_user dependency (session
    cookie based), instead of the global test override every other test uses."""
    original = app.dependency_overrides.pop(get_current_user, None)
    yield TestClient(app)
    if original is not None:
        app.dependency_overrides[get_current_user] = original


def _create_user(email: str) -> int:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, email)
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


def _oauth_login_erroring(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, provider: str = "google"
) -> httpx.Response:
    class _ErroringClient:
        async def authorize_redirect(self, request: Request, redirect_uri: str) -> RedirectResponse:
            return RedirectResponse(url=redirect_uri, status_code=302)

        async def authorize_access_token(self, request: Request) -> dict[str, object]:
            raise OAuthError("access_denied")

    monkeypatch.setattr(oauth_module.oauth, "create_client", lambda name: _ErroringClient())
    client.get(f"/auth/{provider}/start", follow_redirects=False)
    return client.get(f"/auth/{provider}/callback", follow_redirects=False)


def test_oauth_login_existing_user_logs_in(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")

    response = _oauth_login(
        real_client, monkeypatch, email="alice@example.com", provider_user_id="google-alice"
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert real_client.get("/").status_code == 200

    db = TestingSessionLocal()
    try:
        identity = crud.get_oauth_identity(db, "google", "google-alice")
        assert identity is not None
        assert identity.email == "alice@example.com"
    finally:
        db.close()


def test_oauth_callback_error_redirects_with_message(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _oauth_login_erroring(real_client, monkeypatch)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?")
    assert "cancelled" in response.headers["location"]


def test_oauth_login_without_verified_email_shows_error(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="google-alice",
        email_verified=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?")
    assert "verified email" in unquote_plus(response.headers["location"])


def test_oauth_invalid_provider_404(real_client: TestClient) -> None:
    assert real_client.get("/auth/facebook/start").status_code == 404
    assert real_client.get("/auth/facebook/callback").status_code == 404


def test_logout_clears_session(real_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    real_client.post("/logout")

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_signup_form_redirects_when_already_logged_in(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    response = real_client.get("/signup", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_signup_form_starts_with_provider_buttons_disabled(client: TestClient) -> None:
    response = client.get("/signup")
    assert response.status_code == 200
    assert "disabled" in response.text


def test_signup_form_prefills_and_validates_invite_key_from_query_param(
    client: TestClient,
) -> None:
    key = _create_signup_key()

    response = client.get("/signup", params={"invite_key": key})
    assert response.status_code == 200
    assert f'value="{key}"' in response.text
    assert "disabled" not in response.text


def test_signup_form_shows_error_for_bad_invite_key_query_param(client: TestClient) -> None:
    response = client.get("/signup", params={"invite_key": "LEDGER-NOPE-NOPE"})
    assert response.status_code == 200
    assert "invalid or has expired" in response.text
    assert "disabled" in response.text


def test_oauth_signup_success_creates_account_logs_in_and_redeems_key(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _create_signup_key()

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="newuser@example.com",
        provider_user_id="g-new",
        invite_key=key,
        intent="signup",
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


def test_oauth_signup_via_github_creates_account(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _create_signup_key()

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="ghuser@example.com",
        provider_user_id="12345",
        provider="github",
        invite_key=key,
        intent="signup",
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    db = TestingSessionLocal()
    try:
        assert crud.get_user_by_email(db, "ghuser@example.com") is not None
        assert crud.get_oauth_identity(db, "github", "12345") is not None
    finally:
        db.close()


def test_oauth_signup_rejects_missing_key_for_unknown_email(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _oauth_login(
        real_client, monkeypatch, email="newuser@example.com", provider_user_id="g-new"
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/signup?")
    assert "invite key" in unquote_plus(response.headers["location"])

    db = TestingSessionLocal()
    try:
        assert crud.get_user_by_email(db, "newuser@example.com") is None
    finally:
        db.close()


def test_check_signup_key_empty_disables_buttons(client: TestClient) -> None:
    response = client.get("/signup/check-key")
    assert response.status_code == 200
    assert "disabled" in response.text
    assert "invalid or has expired" not in response.text


def test_check_signup_key_valid_enables_buttons(client: TestClient) -> None:
    key = _create_signup_key()

    response = client.get("/signup/check-key", params={"invite_key": key})
    assert response.status_code == 200
    assert "disabled" not in response.text


def test_check_signup_key_invalid_shows_error_and_disables(client: TestClient) -> None:
    response = client.get("/signup/check-key", params={"invite_key": "LEDGER-NOPE-NOPE"})
    assert response.status_code == 200
    assert "disabled" in response.text
    assert "invalid or has expired" in response.text


def test_oauth_signup_rejects_invalid_key(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _oauth_login(
        real_client,
        monkeypatch,
        email="newuser@example.com",
        provider_user_id="g-new",
        invite_key="LEDGER-NOPE-NOPE",
        intent="signup",
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/signup?")
    assert "invalid or has expired" in unquote_plus(response.headers["location"])


def test_oauth_signup_rejects_expired_key(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _create_signup_key(expires_at=datetime.now(UTC) - timedelta(days=1))

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="newuser@example.com",
        provider_user_id="g-new",
        invite_key=key,
        intent="signup",
    )
    assert response.status_code == 303
    assert "invalid or has expired" in unquote_plus(response.headers["location"])


def test_oauth_signup_rejects_exhausted_key(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _create_signup_key(max_uses=1)
    _oauth_login(
        real_client,
        monkeypatch,
        email="first@example.com",
        provider_user_id="g-1",
        invite_key=key,
        intent="signup",
    )
    real_client.post("/logout")

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="second@example.com",
        provider_user_id="g-2",
        invite_key=key,
        intent="signup",
    )
    assert response.status_code == 303
    assert "invalid or has expired" in unquote_plus(response.headers["location"])


def test_oauth_login_auto_links_existing_email_without_key(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An email that already has a User row (e.g. from manage_users.py create,
    or a prior signup) can sign in via OAuth with no invite key -- this is how
    pre-existing accounts get migrated onto OAuth."""
    user_id = _create_user("alice@example.com")

    response = _oauth_login(
        real_client, monkeypatch, email="alice@example.com", provider_user_id="g-alice"
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    db = TestingSessionLocal()
    try:
        identity = crud.get_oauth_identity(db, "google", "g-alice")
        assert identity is not None
        assert identity.user_id == user_id
    finally:
        db.close()


def test_oauth_login_auto_links_email_with_different_casing(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for #71: an operator-created account
    ("Alice@Example.com", however they happened to type it) must still
    auto-link when the OAuth provider returns a differently-cased but
    equivalent verified email -- otherwise this silently creates a second
    account for the same mailbox instead of linking to the existing one."""
    user_id = _create_user("Alice@Example.com")

    response = _oauth_login(
        real_client, monkeypatch, email="alice@example.com", provider_user_id="g-alice"
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    db = TestingSessionLocal()
    try:
        identity = crud.get_oauth_identity(db, "google", "g-alice")
        assert identity is not None
        assert identity.user_id == user_id
        # No duplicate account for the same mailbox under a different casing.
        assert db.query(models.User).filter(models.User.email == "alice@example.com").count() == 1
    finally:
        db.close()


def test_create_user_stores_email_lowercase() -> None:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, "Bob@Example.COM")
        assert user.email == "bob@example.com"
    finally:
        db.close()


def test_get_user_by_email_is_case_insensitive() -> None:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, "carol@example.com")
        found = crud.get_user_by_email(db, "CAROL@Example.com")
        assert found is not None
        assert found.id == user.id
    finally:
        db.close()


def test_oauth_login_links_second_provider_to_same_account(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _create_signup_key()
    _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="g-alice",
        provider="google",
        invite_key=key,
        intent="signup",
    )
    real_client.post("/logout")

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="gh-alice",
        provider="github",
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "alice@example.com")
        assert user is not None
        google_identity = crud.get_oauth_identity(db, "google", "g-alice")
        github_identity = crud.get_oauth_identity(db, "github", "gh-alice")
        assert google_identity is not None and github_identity is not None
        assert google_identity.user_id == github_identity.user_id == user.id
    finally:
        db.close()


def test_oauth_signup_blocks_already_linked_identity(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/signup for a Google identity that's already linked to an account
    doesn't silently log in -- it bounces to /login with an explanatory
    message, so "wrong button" clicks don't look like a fresh account."""
    key = _create_signup_key()
    _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="g-alice",
        invite_key=key,
        intent="signup",
    )
    real_client.post("/logout")

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="g-alice",
        intent="signup",
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?")
    assert "already have an account" in unquote_plus(response.headers["location"])

    # Bounced, not logged in.
    home = real_client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/login"


def test_oauth_signup_blocks_matching_email_different_provider(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same block, but for the auto-link case: signing up (not logging in)
    with a provider identity whose email already has an account."""
    _create_user("alice@example.com")

    response = _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="gh-alice",
        provider="github",
        intent="signup",
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?")
    assert "already have an account" in unquote_plus(response.headers["location"])

    db = TestingSessionLocal()
    try:
        # No identity got linked -- the block happens before that step.
        assert crud.get_oauth_identity(db, "github", "gh-alice") is None
    finally:
        db.close()


def test_keep_signed_in_survives_the_default_idle_timeout(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="g-1",
        keep_signed_in=True,
    )

    past_default_idle = 1000.0 + auth.SESSION_IDLE_TIMEOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: past_default_idle)
    assert real_client.get("/").status_code == 200


def test_keep_signed_in_still_expires_after_its_own_absolute_cap(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    _oauth_login(
        real_client,
        monkeypatch,
        email="alice@example.com",
        provider_user_id="g-1",
        keep_signed_in=True,
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
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    future = 1000.0 + auth.SESSION_IDLE_TIMEOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: future)

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_activity_slides_the_idle_window(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

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
    _create_user("alice@example.com")

    monkeypatch.setattr(auth.time, "time", lambda: 1000.0)
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

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


def test_cross_user_data_isolation(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _create_user("bob@example.com")

    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-alice")
    create = real_client.post("/channels", data={"name": "Alice Bank", "color": "#8a8a8a"})
    assert "Alice Bank" in create.text

    real_client.post("/logout")
    _oauth_login(real_client, monkeypatch, email="bob@example.com", provider_user_id="g-bob")

    expenses_page = real_client.get("/expenses")
    assert "Alice Bank" not in expenses_page.text


def test_account_page_requires_login(real_client: TestClient) -> None:
    response = real_client.get("/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def _png_bytes() -> bytes:
    # Valid 1x1 transparent PNG.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360606060000000050001a5f6454000000000"
        "49454e44ae426082"
    )


def test_update_profile_persists_all_fields(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

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


def test_update_profile_unchecked_notify_box_is_saved_as_false(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

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


def test_update_profile_rejects_invalid_currency(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    response = real_client.post("/account/profile", data={"currency_code": "XXX", "timezone": ""})
    assert response.status_code == 400
    assert "valid currency" in response.text


def test_update_profile_rejects_invalid_timezone(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    response = real_client.post(
        "/account/profile",
        data={"currency_code": "PHP", "timezone": "Not/A_Real_Zone"},
    )
    assert response.status_code == 400
    assert "valid timezone" in response.text


def test_upload_avatar_is_served_and_shown_in_rail(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

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


def test_upload_avatar_rejects_non_image_files(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")

    response = real_client.post(
        "/account/avatar", files={"avatar": ("evil.txt", b"not an image", "text/plain")}
    )
    assert response.status_code == 400


def test_remove_avatar_falls_back_to_icon(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _oauth_login(real_client, monkeypatch, email="alice@example.com", provider_user_id="g-1")
    real_client.post("/account/avatar", files={"avatar": ("avatar.png", _png_bytes(), "image/png")})

    removed = real_client.delete("/account/avatar")
    assert removed.status_code == 200
    assert 'src="/account/avatar"' not in removed.text

    missing = real_client.get("/account/avatar")
    assert missing.status_code == 404

    home = real_client.get("/")
    assert 'src="/account/avatar"' not in home.text
