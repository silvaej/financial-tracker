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


def _set_funding_source(client: TestClient, channel_id: str, name: str, source_id: str) -> None:
    response = client.patch(
        f"/channels/{channel_id}",
        data={"name": name, "color": "#8a8a8a", "funding_source_channel_id": source_id},
    )
    assert response.status_code == 200


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


def test_add_transfer_row_suggests_amount_needed_to_cover_channel_expenses(
    client: TestClient,
) -> None:
    """B has a 500 expense and no income/transfers yet, so the suggested
    top-up for B (data-needed on its <option>) should be exactly 500.00.
    """
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.get("/")
    assert response.status_code == 200
    match = re.search(rf'value="{b}"\s+data-needed="([\d.]+)"', response.text)
    assert match is not None
    assert match.group(1) == "500.00"

    # A is the receiving channel with untouched income, so it needs no top-up.
    match_a = re.search(rf'value="{a}"\s+data-needed="([\d.]+)"', response.text)
    assert match_a is not None
    assert match_a.group(1) == "0.00"


def test_generate_transfers_creates_transfer_for_funded_channel_shortfall(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    _set_funding_source(client, b, "Channel B", a)
    period_id = _create_payout_period(client, "15th", "1000", a)

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

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    first = client.post(f"/transfers/generate/{period_id}")
    second = client.post(f"/transfers/generate/{period_id}")
    assert first.status_code == 200
    assert second.status_code == 200
    # Only one transfer row should exist, not two stacked from repeated generation.
    assert len(re.findall(r'hx-delete="/transfers/\d+"', second.text)) == 1


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
    assert not re.search(r'hx-delete="/transfers/\d+"', response.text)


def _transfer_amount(html: str, from_name: str, to_name: str) -> str | None:
    """Find the amount cell in a transfer row rendered as From-name / To-name / amount."""
    pattern = (
        rf"{re.escape(from_name)}</td>\s*<td>.*?{re.escape(to_name)}</td>\s*"
        r'<td class="num">\s*<span class="view-transfer-\d+">&#8369;([\d,]+\.\d\d)</span>'
    )
    match = re.search(pattern, html, re.DOTALL)
    return match.group(1) if match else None


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
    assert not re.search(r'hx-delete="/transfers/\d+"', response.text)
