from fastapi.testclient import TestClient


def test_signup_check_key_is_rate_limited(client: TestClient) -> None:
    """Regression test for #72: the unauthenticated auth surface (here,
    /signup/check-key) must reject a burst of requests from the same client
    past its configured per-minute limit, with a plain-string `detail` (not
    slowapi's default {"error": ...} shape -- see app/main.py's
    rate_limit_exceeded_handler)."""
    responses = [client.get("/signup/check-key", params={"invite_key": "x"}) for _ in range(31)]

    assert all(r.status_code == 200 for r in responses[:30])
    limited = responses[30]
    assert limited.status_code == 429
    detail = limited.json()["detail"]
    assert isinstance(detail, str)
    assert "too many requests" in detail.lower()


def test_oauth_start_is_rate_limited(client: TestClient) -> None:
    responses = [client.get("/auth/google/start", follow_redirects=False) for _ in range(11)]

    assert all(r.status_code == 302 for r in responses[:10])
    assert responses[10].status_code == 429
