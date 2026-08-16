import pytest
from fastapi.testclient import TestClient


def test_security_headers_present_on_every_response(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_only_set_on_vercel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    assert "Strict-Transport-Security" not in client.get("/health").headers

    monkeypatch.setenv("VERCEL", "1")
    assert "max-age" in client.get("/health").headers["Strict-Transport-Security"]
