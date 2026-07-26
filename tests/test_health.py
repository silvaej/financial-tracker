from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_requires_no_auth(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/health", follow_redirects=False)
    assert response.status_code == 200
