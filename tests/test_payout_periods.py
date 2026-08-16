import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def test_create_payout_period(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "36100.46", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 200
    assert "15th" in response.text
    assert "36100" in response.text


def test_create_payout_period_with_no_channel(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "30th", "income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 200
    assert "30th" in response.text


def test_create_payout_period_rejects_whitespace_only_label(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "   ", "income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 422


def test_create_payout_period_rejects_negative_income(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "-100", "receiving_channel_id": ""},
    )
    assert response.status_code == 422


def test_update_payout_period_rejects_negative_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "-2000", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 422


def test_update_payout_period_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "2000", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 200
    assert "2000" in response.text


def test_delete_empty_payout_period_succeeds(client: TestClient) -> None:
    create = client.post(
        "/payout-periods",
        data={"label": "Empty Period", "income_amount": "0", "receiving_channel_id": ""},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.delete(f"/payout-periods/{period_id}")
    assert response.status_code == 200
    assert "Empty Period" not in response.text


def test_delete_payout_period_in_use_by_expense_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "5000",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )

    response = client.delete(f"/payout-periods/{period_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]
