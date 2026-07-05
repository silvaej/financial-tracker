import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    # Channels are listed alphabetically, so grabbing the first "/channels/{id}"
    # match in the page breaks once more than one channel exists. Anchor the
    # match to this channel's own row by starting from its name input.
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, label: str, income: str, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": label, "income_amount": income, "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def test_create_update_delete_transfer(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)

    create = client.post(
        "/transfers",
        data={
            "payout_period_id": period_id,
            "from_channel_id": a,
            "to_channel_id": b,
            "amount": "300",
        },
    )
    assert create.status_code == 200
    match = re.search(r"/transfers/(\d+)", create.text)
    assert match is not None
    transfer_id = match.group(1)

    updated = client.patch(f"/transfers/{transfer_id}", data={"amount": "400"})
    assert updated.status_code == 200

    deleted = client.delete(f"/transfers/{transfer_id}")
    assert deleted.status_code == 200


def test_channel_balances_reflect_income_transfers_and_expenses(client: TestClient) -> None:
    """Worked example: A receives 1000 income, sends 300 to B.
    A also has a 100 expense, B has a 50 expense.
    Expected: A net = 1000 - 300 - 100 = 600. B net = 300 - 50 = 250.
    """
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)

    client.post(
        "/transfers",
        data={
            "payout_period_id": period_id,
            "from_channel_id": a,
            "to_channel_id": b,
            "amount": "300",
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "A bill",
            "amount": "100",
            "payout_period_id": period_id,
            "channel_id": a,
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "B bill",
            "amount": "50",
            "payout_period_id": period_id,
            "channel_id": b,
        },
    )

    response = client.get("/")
    assert response.status_code == 200
    assert "600.00" in response.text
    assert "250.00" in response.text
