from fastapi.testclient import TestClient


def test_root_renders_overview(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="overview-page"' in response.text


def test_expenses_has_its_own_route(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert 'id="expenses-page"' in response.text


def test_boosted_nav_request_returns_fragment_only(client: TestClient) -> None:
    response = client.get("/goals", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert 'id="goals-page"' in response.text
    assert "<html" not in response.text
    assert "<nav" not in response.text


def test_plain_request_returns_full_page(client: TestClient) -> None:
    response = client.get("/goals")
    assert response.status_code == 200
    assert 'id="goals-page"' in response.text
    assert "<html" in response.text
    assert 'id="rail"' in response.text
