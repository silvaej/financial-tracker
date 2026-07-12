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


def _set_funding_source(client: TestClient, channel_id: str, name: str, source_id: str) -> None:
    response = client.patch(
        f"/channels/{channel_id}",
        data={"name": name, "color": "#8a8a8a", "funding_source_channel_id": source_id},
    )
    assert response.status_code == 200


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


def test_generate_transfers_creates_transfer_for_funded_channel_shortfall(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    _set_funding_source(client, b, "Channel B", a)
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert "500.00" in response.text
    assert "HX-Trigger" not in response.headers


def test_generate_transfers_replaces_existing_transfers_not_duplicates(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    _set_funding_source(client, b, "Channel B", a)
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    first = client.post(f"/transfers/generate/{period_id}")
    second = client.post(f"/transfers/generate/{period_id}")
    assert first.status_code == 200
    assert second.status_code == 200
    # Only one transfer row should exist, not two stacked from repeated generation.
    assert len(re.findall(r'canvas-edge-label"\s+data-edge-id="transfer-\d+"', second.text)) == 1


def test_generate_transfers_reports_channels_without_funding_source(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert "Channel B" in response.headers["HX-Trigger"]
    assert not re.search(r'canvas-edge-label"\s+data-edge-id="transfer-\d+"', response.text)


def _channel_node_id(html: str, name: str) -> str:
    """Find a channel's canvas node id by the channel name shown in its badge title."""
    for match in re.finditer(r'data-node-id="channel-(\d+)"', html):
        window = html[match.end() : match.end() + 600]
        if f'title="{name}"' in window:
            return match.group(1)
    raise AssertionError(f"channel node for {name!r} not found")


def _transfer_amount(html: str, from_name: str, to_name: str) -> str | None:
    """Find a transfer's edge-label amount by its from/to channel names."""
    from_id = _channel_node_id(html, from_name)
    to_id = _channel_node_id(html, to_name)
    line_match = re.search(
        rf'data-edge-id="transfer-(\d+)"\s+data-from="channel-{from_id}"\s+'
        rf'data-to="channel-{to_id}"',
        html,
    )
    if line_match is None:
        return None
    edge_id = line_match.group(1)
    label_match = re.search(
        rf'class="canvas-edge-label"\s+data-edge-id="transfer-{edge_id}"[\s\S]*?&#8369;([\d,]+\.\d\d)',
        html,
    )
    return label_match.group(1) if label_match else None


def test_generate_transfers_rolls_up_multi_hop_chain(client: TestClient) -> None:
    """Root -> Mid -> {LeafA, LeafB}. Mid also has its own small expense.
    Root->Mid must carry Mid's own expense plus everything Mid forwards on;
    Mid->LeafA and Mid->LeafB carry only each leaf's own expense.
    """
    root = _create_channel(client, "Root")
    mid = _create_channel(client, "Mid")
    leaf_a = _create_channel(client, "LeafA")
    leaf_b = _create_channel(client, "LeafB")
    _set_funding_source(client, mid, "Mid", root)
    _set_funding_source(client, leaf_a, "LeafA", mid)
    _set_funding_source(client, leaf_b, "LeafB", mid)
    period_id = _create_payout_period(client, "15th", "1000", root)
    _place_channel(client, period_id, root)
    _place_channel(client, period_id, mid)
    _place_channel(client, period_id, leaf_a)
    _place_channel(client, period_id, leaf_b)

    client.post(
        "/expenses",
        data={"name": "Mid bill", "amount": "20", "payout_period_id": period_id, "channel_id": mid},
    )
    client.post(
        "/expenses",
        data={
            "name": "A bill",
            "amount": "100",
            "payout_period_id": period_id,
            "channel_id": leaf_a,
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "B bill",
            "amount": "50",
            "payout_period_id": period_id,
            "channel_id": leaf_b,
        },
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert "HX-Trigger" not in response.headers
    assert _transfer_amount(response.text, "Root", "Mid") == "170.00"
    assert _transfer_amount(response.text, "Mid", "LeafA") == "100.00"
    assert _transfer_amount(response.text, "Mid", "LeafB") == "50.00"


def test_generate_transfers_funds_pure_pass_through_channel(client: TestClient) -> None:
    """A pass-through channel with zero expenses of its own must still receive
    an inbound transfer sized to exactly what it needs to forward downstream.
    """
    root = _create_channel(client, "Root")
    passthrough = _create_channel(client, "Passthrough")
    leaf = _create_channel(client, "Leaf")
    _set_funding_source(client, passthrough, "Passthrough", root)
    _set_funding_source(client, leaf, "Leaf", passthrough)
    period_id = _create_payout_period(client, "15th", "1000", root)
    _place_channel(client, period_id, root)
    _place_channel(client, period_id, passthrough)
    _place_channel(client, period_id, leaf)

    client.post(
        "/expenses",
        data={
            "name": "Leaf bill",
            "amount": "500",
            "payout_period_id": period_id,
            "channel_id": leaf,
        },
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert _transfer_amount(response.text, "Root", "Passthrough") == "500.00"
    assert _transfer_amount(response.text, "Passthrough", "Leaf") == "500.00"


def test_generate_transfers_reports_circular_funding_without_hanging(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    _set_funding_source(client, a, "Channel A", b)
    _set_funding_source(client, b, "Channel B", a)
    period_id = _create_payout_period(client, "15th", "1000", a)

    client.post(
        "/expenses",
        data={"name": "A bill", "amount": "100", "payout_period_id": period_id, "channel_id": a},
    )
    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "50", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert "Circular funding" in response.headers["HX-Trigger"]
    assert "Channel A" in response.headers["HX-Trigger"]
    assert "Channel B" in response.headers["HX-Trigger"]
    assert not re.search(r'canvas-edge-label"\s+data-edge-id="transfer-\d+"', response.text)


def test_generate_transfers_includes_goal_contribution_on_its_channel(
    client: TestClient,
) -> None:
    """A goal parked on a channel with no expenses of its own should still pull
    a transfer sized to its per-payout contribution when generating, exactly
    like a pure pass-through channel would.
    """
    root = _create_channel(client, "Root")
    savings = _create_channel(client, "Savings")
    _set_funding_source(client, savings, "Savings", root)
    period_id = _create_payout_period(client, "15th", "1000", root)
    # Second payout period so the goal's monthly amount splits across 2.
    _create_payout_period(client, "30th", "0", root)
    _place_channel(client, period_id, root)
    _place_channel(client, period_id, savings)

    client.post(
        "/goals",
        data={
            "name": "Emergency Fund",
            "target": "1000",
            "months": "1",
            "channel_id": savings,
        },
    )

    response = client.post(f"/transfers/generate/{period_id}")
    assert response.status_code == 200
    assert "HX-Trigger" not in response.headers
    assert _transfer_amount(response.text, "Root", "Savings") == "500.00"
