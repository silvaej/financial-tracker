from fastapi.testclient import TestClient


def test_create_channel_appears_on_page(client: TestClient) -> None:
    response = client.post("/channels", data={"name": "BPI", "color": "#B8122B"})
    assert response.status_code == 200
    assert "BPI" in response.text


def test_update_channel_renames_it(client: TestClient) -> None:
    create = client.post("/channels", data={"name": "Maya", "color": "#0FA968"})
    assert "Maya" in create.text

    import re

    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    response = client.patch(
        f"/channels/{channel_id}", data={"name": "Maya Savings", "color": "#0FA968"}
    )
    assert response.status_code == 200
    assert "Maya Savings" in response.text


def test_delete_channel(client: TestClient) -> None:
    create = client.post("/channels", data={"name": "Temp Channel", "color": "#8a8a8a"})
    import re

    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    response = client.delete(f"/channels/{channel_id}")
    assert response.status_code == 200
    assert "Temp Channel" not in response.text


def test_delete_channel_in_use_by_payout_period_is_rejected(client: TestClient) -> None:
    import re

    create = client.post("/channels", data={"name": "BDO", "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )

    response = client.delete(f"/channels/{channel_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]
