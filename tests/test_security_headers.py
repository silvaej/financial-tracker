from urllib.parse import urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.oauth import OAUTH_REDIRECT_ORIGINS


def test_security_headers_present_on_every_response(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def _form_action(response: httpx.Response) -> list[str]:
    directive = next(
        part
        for part in response.headers["Content-Security-Policy"].split("; ")
        if part.startswith("form-action ")
    )
    return directive.split()


def test_csp_form_action_allows_the_github_redirect_target(client: TestClient) -> None:
    """Regression test for #129: `form-action 'self'` alone broke login in
    Chrome, which enforces form-action against every hop of a redirect chain
    -- login.html submits a real <form> to /auth/{provider}/start, which 302s
    to the provider's own origin.

    Asserts against the redirect's *actual* Location header rather than a
    hardcoded origin, so it fails if github's authorize_url moves without
    form-action following it. GitHub only: its authorize_url is pinned in
    app/oauth.py, so this stays offline. Google's comes from a live OIDC
    discovery fetch, which would make this suite network-dependent -- covered
    by the constant-based test below instead."""
    response = client.get("/auth/github/start", follow_redirects=False)
    assert response.status_code == 302

    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" in _form_action(response)


def test_csp_form_action_allows_every_declared_oauth_origin(client: TestClient) -> None:
    """Guards the realistic drift case for #129: a provider gets added to
    app/oauth.py's register() calls and OAUTH_REDIRECT_ORIGINS, but the CSP
    isn't updated -- which breaks login in Chrome only, silently, with no
    server-side error. Nothing else in the suite would catch that, since the
    OAuth tests fake the provider exchange entirely (tests/conftest.py)."""
    form_action = _form_action(client.get("/health"))
    assert OAUTH_REDIRECT_ORIGINS, "expected at least one provider origin to be declared"
    for origin in OAUTH_REDIRECT_ORIGINS:
        assert origin in form_action


def test_hsts_only_set_on_vercel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    assert "Strict-Transport-Security" not in client.get("/health").headers

    monkeypatch.setenv("VERCEL", "1")
    assert "max-age" in client.get("/health").headers["Strict-Transport-Security"]
