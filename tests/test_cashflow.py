from fastapi.testclient import TestClient


def test_cashflow_page_renders(client: TestClient) -> None:
    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "Cash Flow" in response.text
    assert 'id="cashflow-page"' in response.text


def test_expenses_page_no_longer_shows_cash_flow(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert 'id="cashflow-page"' not in response.text
    assert "Generate transfers" not in response.text
