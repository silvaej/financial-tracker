from fastapi.testclient import TestClient


def test_overview_empty_state(client: TestClient) -> None:
    response = client.get("/overview")
    assert response.status_code == 200
    assert "No goals yet" in response.text
    assert "No credit lines yet" in response.text


def test_overview_kpi_totals(client: TestClient) -> None:
    client.post("/assets", data={"name": "BPI IMI", "amount": "11210.80"})
    client.post("/assets", data={"name": "Maya TD", "amount": "5053.43"})
    client.post(
        "/credit", data={"name": "BPI Blue Mastercard", "limit": "196000", "used": "12367.39"}
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "16,264.23" in response.text  # total assets
    assert "12,367.39" in response.text  # total liabilities
    assert "3,896.84" in response.text  # net worth


def test_overview_net_worth_negative_uses_neg_class(client: TestClient) -> None:
    client.post("/assets", data={"name": "Small Asset", "amount": "100"})
    client.post("/credit", data={"name": "Big Card", "limit": "10000", "used": "5000"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "card-value-neg" in response.text


def test_overview_shows_funded_pill_for_completed_goal(client: TestClient) -> None:
    client.post(
        "/goals",
        data={"name": "Fully Funded", "target": "1000", "allocated": "1000", "months": "1"},
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "pill-gold" in response.text
    assert "Funded" in response.text


def test_overview_does_not_show_funded_pill_for_incomplete_goal(client: TestClient) -> None:
    client.post(
        "/goals", data={"name": "In Progress", "target": "1000", "allocated": "250", "months": "1"}
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "pill-gold" not in response.text


def test_overview_shows_warn_pill_for_near_limit_credit(client: TestClient) -> None:
    client.post("/credit", data={"name": "Near Limit", "limit": "1000", "used": "850"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "warn-amber" in response.text
    assert "Near limit" in response.text


def test_overview_shows_warn_pill_for_over_limit_credit(client: TestClient) -> None:
    client.post("/credit", data={"name": "Over Limit", "limit": "1000", "used": "1200"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "warn-red" in response.text
    assert "Over limit" in response.text


def test_unknown_section_still_404s(client: TestClient) -> None:
    response = client.get("/nonsense")
    assert response.status_code == 404
