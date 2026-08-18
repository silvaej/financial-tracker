import re

from fastapi.testclient import TestClient


def test_create_asset_appears_on_page(client: TestClient) -> None:
    response = client.post("/assets", data={"name": "BPI IMI", "amount": "11210.80"})
    assert response.status_code == 200
    assert "BPI IMI" in response.text


def test_update_asset_renames_and_changes_amount(client: TestClient) -> None:
    create = client.post("/assets", data={"name": "Maya TD", "amount": "1000"})
    match = re.search(r'/assets/(\d+)"', create.text)
    assert match is not None
    asset_id = match.group(1)

    response = client.patch(
        f"/assets/{asset_id}", data={"name": "Maya Time Deposit", "amount": "5053.43"}
    )
    assert response.status_code == 200
    assert "Maya Time Deposit" in response.text
    assert "Maya TD" not in response.text


def test_create_asset_rejects_zero_or_negative_amount(client: TestClient) -> None:
    for amount in ("0", "-11210.80"):
        response = client.post("/assets", data={"name": "BPI IMI", "amount": amount})
        assert response.status_code == 422


def test_create_asset_rejects_whitespace_only_name(client: TestClient) -> None:
    response = client.post("/assets", data={"name": "   ", "amount": "1000"})
    assert response.status_code == 422


def test_delete_asset(client: TestClient) -> None:
    create = client.post("/assets", data={"name": "Temp Asset", "amount": "500"})
    match = re.search(r'/assets/(\d+)"', create.text)
    assert match is not None
    asset_id = match.group(1)

    response = client.delete(f"/assets/{asset_id}")
    assert response.status_code == 200
    assert "Temp Asset" not in response.text


def test_assets_empty_state_shows_placeholder_text(client: TestClient) -> None:
    response = client.get("/assets")
    assert response.status_code == 200
    assert "No assets yet" in response.text


def test_total_assets_kpi_reflects_sum(client: TestClient) -> None:
    client.post("/assets", data={"name": "Asset A", "amount": "100.50"})
    client.post("/assets", data={"name": "Asset B", "amount": "200.25"})

    response = client.get("/assets")
    assert response.status_code == 200
    assert "300.75" in response.text


def test_total_assets_card_explains_what_it_means(client: TestClient) -> None:
    """Regression test for #136 (same gap covered on Overview)."""
    response = client.get("/assets")
    assert response.status_code == 200
    assert 'title="Sum of everything below' in response.text
