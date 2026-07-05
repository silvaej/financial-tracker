import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, label: str, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": label, "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def test_create_and_delete_expense(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Groceries",
            "amount": "150.75",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert create.status_code == 200
    assert "Groceries" in create.text
    assert "150.75" in create.text

    match = re.search(r"/expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    response = client.delete(f"/expenses/{expense_id}")
    assert response.status_code == 200
    assert "Groceries" not in response.text
