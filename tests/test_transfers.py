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
    # Periods are listed in ascending display_order, so the just-created one
    # (highest display_order) is the last match once more than one exists.
    matches = re.findall(r"/payout-periods/(\d+)", response.text)
    assert matches
    return matches[-1]


def _place_channel(client: TestClient, period_id: str, channel_id: str) -> None:
    response = client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "0", "y": "0"},
    )
    assert response.status_code == 200


def test_create_update_delete_transfer(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

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
    match = re.search(r'data-edge-id="transfer-(\d+)"', create.text)
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
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

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

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "600.00" in response.text
    assert "250.00" in response.text


def test_cashflow_canvas_shows_channel_nodes_with_balances(
    client: TestClient,
) -> None:
    """B has a 500 expense and no income/transfers yet, so its canvas node
    should show a -500.00 balance; A (the receiving channel) should show
    its untouched 1000 income.
    """
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert f'data-node-id="channel-{a}"' in response.text
    assert f'data-node-id="channel-{b}"' in response.text
    assert "1,000.00" in response.text
    assert "-&#8369;500.00" in response.text
