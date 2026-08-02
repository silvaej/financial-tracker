import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import models
from app import oauth as oauth_module
from app.auth import get_current_user
from app.csrf import csrf_protect
from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_USER_ID = 1


def _override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _override_get_current_user() -> models.User:
    db = TestingSessionLocal()
    try:
        user = db.get(models.User, TEST_USER_ID)
        assert user is not None
        return user
    finally:
        db.close()


async def _override_csrf_protect() -> None:
    return None


app.dependency_overrides[get_db] = _override_get_db
app.dependency_overrides[get_current_user] = _override_get_current_user
app.dependency_overrides[csrf_protect] = _override_csrf_protect


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    # Onboarding already "complete" -- this fixture's user backs nearly every
    # test in the suite, most of which have nothing to do with onboarding and
    # would otherwise get redirected out of Overview by needs_onboarding().
    # Tests that actually exercise onboarding (tests/test_auth.py) create
    # their own fresh user via crud.create_user() instead of this fixture.
    db.add(
        models.User(
            id=TEST_USER_ID,
            email="test@example.com",
            onboarding_completed_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class _FakeOAuthResponse:
    """Stands in for an httpx.Response -- only .json() is ever used."""

    def __init__(self, data: Any) -> None:
        self._data = data

    def json(self) -> Any:
        return self._data


class _FakeOAuthClient:
    """Stands in for authlib's StarletteOAuth2App -- no real network calls."""

    def __init__(
        self, token: dict[str, Any], get_responses: dict[str, _FakeOAuthResponse] | None = None
    ) -> None:
        self._token = token
        self._get_responses = get_responses or {}

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> RedirectResponse:
        return RedirectResponse(url=redirect_uri, status_code=302)

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        return self._token

    async def get(self, url: str, token: Any = None) -> _FakeOAuthResponse:
        return self._get_responses[url]


def _fake_oauth_client_for(
    provider: str, email: str | None, provider_user_id: str, email_verified: bool
) -> _FakeOAuthClient:
    if provider == "google":
        userinfo = {"sub": provider_user_id, "email": email, "email_verified": email_verified}
        return _FakeOAuthClient({"userinfo": userinfo})
    emails = [{"email": email, "primary": True, "verified": email_verified}] if email else []
    return _FakeOAuthClient(
        {},
        get_responses={
            "user": _FakeOAuthResponse({"id": provider_user_id}),
            "user/emails": _FakeOAuthResponse(emails),
        },
    )


def oauth_login(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str | None,
    provider_user_id: str,
    provider: str = "google",
    invite_key: str = "",
    keep_signed_in: bool = False,
    email_verified: bool = True,
    intent: str = "login",
) -> httpx.Response:
    """Drives a client through /auth/<provider>/start + /callback with a faked
    provider exchange -- see app/routers/oauth.py. Reused by every test that
    needs a real (session-cookie based) login without hitting a real provider.
    `intent` mirrors the hidden form field login.html/signup.html send."""
    fake_client = _fake_oauth_client_for(provider, email, provider_user_id, email_verified)
    monkeypatch.setattr(oauth_module.oauth, "create_client", lambda name: fake_client)

    client.get(
        f"/auth/{provider}/start",
        params={"invite_key": invite_key, "keep_signed_in": keep_signed_in, "intent": intent},
        follow_redirects=False,
    )
    return client.get(f"/auth/{provider}/callback", follow_redirects=False)
