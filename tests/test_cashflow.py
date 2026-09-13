import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_cycle(client: TestClient, payout_day: int, income: str, channel_id: str) -> str:
    response = client.post(
        "/cycles",
        data={
            "income_amount": income,
            "receiving_channel_id": channel_id,
            "payout_day": str(payout_day),
        },
    )
    # Periods are listed in ascending payout_day, so the just-created one
    # (highest payout_day among these fixtures) is the last match once more
    # than one exists.
    matches = re.findall(r"/cycles/(\d+)", response.text)
    assert matches
    return matches[-1]


def test_cashflow_page_renders(client: TestClient) -> None:
    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "Cash Flow" in response.text
    assert 'id="cashflow-page"' in response.text


def test_expenses_page_no_longer_shows_cash_flow(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert 'id="cashflow-page"' not in response.text
    assert "Generate transfers" not in response.text


def test_channel_balance_carries_over_to_next_cycle(client: TestClient) -> None:
    """A ends period 1 with 1000 leftover (pure income, no expenses/transfers), so
    period 2 (also receiving 500 income) should show a 1500 ending balance."""
    a = _create_channel(client, "Channel A")
    cycle_1 = _create_cycle(client, 15, "1000", a)
    cycle_2 = _create_cycle(client, 30, "500", a)
    client.post(f"/channels/{a}/placement", data={"cycle_id": cycle_1, "x": "0", "y": "0"})
    client.post(f"/channels/{a}/placement", data={"cycle_id": cycle_2, "x": "0", "y": "0"})

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "1,000.00" in response.text
    assert "1,500.00" in response.text
    assert "carried in" in response.text


def test_new_channel_starts_in_toolbox_not_on_canvas(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    _create_cycle(client, 15, "1000", a)

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert 'class="toolbox-item"' in response.text
    assert f'data-node-id="channel-{a}"' in response.text
    assert f'data-position-url="/channels/{a}/placement"' not in response.text


def test_placing_channel_moves_it_from_toolbox_to_canvas(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    cycle_id = _create_cycle(client, 15, "1000", a)

    response = client.post(
        f"/channels/{a}/placement", data={"cycle_id": cycle_id, "x": "50", "y": "60"}
    )
    assert response.status_code == 200
    assert f'data-position-url="/channels/{a}/placement"' in response.text
    assert 'data-x="50.0"' in response.text
    assert 'data-y="60.0"' in response.text


def test_unfunded_channel_shows_warning(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    cycle_id = _create_cycle(client, 15, "0", a)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "cycle_id": cycle_id, "channel_id": b},
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "Channel B is short this payout" in response.text


def test_underfunded_goal_shows_warning(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    _create_cycle(client, 15, "1000", a)
    client.post(
        "/goals",
        data={"name": "Emergency Fund", "target": "1000", "months": "1", "channel_id": a},
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "Emergency Fund isn't fully funded this payout" in response.text


def test_fully_funded_goal_has_no_warning(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    cycle_id = _create_cycle(client, 15, "1000", a)
    goal = client.post(
        "/goals",
        data={"name": "Emergency Fund", "target": "1000", "months": "1", "channel_id": a},
    )
    match = re.search(r'/goals/(\d+)"', goal.text)
    assert match is not None
    goal_id = match.group(1)

    client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": a,
            "cycle_id": cycle_id,
            "amount": "1000",
        },
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "isn't fully funded" not in response.text


# --- Onboarding nudge (#138) --------------------------------------------------


def test_shows_nudge_when_no_transfers_yet(client: TestClient) -> None:
    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "nudge-banner" in response.text
    assert "Route your money onward" in response.text


def test_nudge_disappears_once_a_transfer_exists(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    cycle_id = _create_cycle(client, 15, "1000", a)

    response = client.post(
        "/transfers",
        data={
            "cycle_id": cycle_id,
            "from_channel_id": a,
            "to_channel_id": b,
            "amount": "100",
        },
    )
    assert "nudge-banner" not in response.text


def test_dismissing_nudge_clears_it_even_while_still_empty(client: TestClient) -> None:
    response = client.post("/cashflow/nudge/dismiss")
    assert response.status_code == 200
    assert "nudge-banner" not in response.text

    response = client.get("/cashflow")
    assert "nudge-banner" not in response.text
