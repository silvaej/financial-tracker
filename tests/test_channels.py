import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str, color: str = "#8a8a8a") -> str:
    create = client.post("/channels", data={"name": name, "color": color})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', create.text, re.DOTALL)
    assert match is not None
    return match.group(1)


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


def test_create_channel_with_funding_source(client: TestClient) -> None:
    source_id = _create_channel(client, "BPI")
    response = client.post(
        "/channels",
        data={
            "name": "BPI Credit Card",
            "color": "#8a8a8a",
            "funding_source_channel_id": source_id,
        },
    )
    assert response.status_code == 200
    assert "BPI Credit Card" in response.text


def test_update_channel_funding_source(client: TestClient) -> None:
    source_id = _create_channel(client, "BPI")
    target_id = _create_channel(client, "Maya Black")

    response = client.patch(
        f"/channels/{target_id}",
        data={"name": "Maya Black", "color": "#8a8a8a", "funding_source_channel_id": source_id},
    )
    assert response.status_code == 200
    assert "BPI" in response.text


def test_update_channel_self_funding_source_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "Solo Channel")

    response = client.patch(
        f"/channels/{channel_id}",
        data={
            "name": "Solo Channel",
            "color": "#8a8a8a",
            "funding_source_channel_id": channel_id,
        },
    )
    assert response.status_code == 400
    assert "fund itself" in response.json()["detail"]


def _create_payout_period(client: TestClient, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "0", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def test_channel_starts_unplaced_and_can_be_placed_then_repositioned(
    client: TestClient,
) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, channel_id)

    # Not placed yet -> no canvas node, just a toolbox entry.
    before = client.get("/cashflow")
    assert f'data-position-url="/channels/{channel_id}/placement"' not in before.text
    assert "BPI" in before.text

    place = client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "10", "y": "20"},
    )
    assert place.status_code == 200
    assert 'data-x="10.0"' in place.text
    assert 'data-y="20.0"' in place.text

    reposition = client.patch(
        f"/channels/{channel_id}/placement",
        json={"payout_period_id": int(period_id), "x": 123.5, "y": 45.0},
    )
    assert reposition.status_code == 204

    page = client.get("/cashflow")
    assert 'data-x="123.5"' in page.text
    assert 'data-y="45.0"' in page.text


def test_remove_channel_placement_returns_it_to_the_toolbox(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, channel_id)
    client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "10", "y": "20"},
    )

    removed = client.delete(f"/channels/{channel_id}/placement?payout_period_id={period_id}")
    assert removed.status_code == 200
    assert f'data-position-url="/channels/{channel_id}/placement"' not in removed.text
    assert "BPI" in removed.text


def test_delete_channel_used_as_funding_source_is_rejected(client: TestClient) -> None:
    source_id = _create_channel(client, "BPI")
    target_id = _create_channel(client, "Maya Black")
    client.patch(
        f"/channels/{target_id}",
        data={"name": "Maya Black", "color": "#8a8a8a", "funding_source_channel_id": source_id},
    )

    response = client.delete(f"/channels/{source_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]
