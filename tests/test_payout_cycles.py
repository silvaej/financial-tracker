import re

from fastapi.testclient import TestClient

from app import crud, schemas
from tests.conftest import TEST_USER_ID, TestingSessionLocal


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
    matches = re.findall(r"/payout-periods/(\d+)", response.text)
    assert matches
    return matches[-1]


def test_history_page_shows_live_template_with_no_cycles_closed(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", "1000", channel_id)

    response = client.get(f"/payout-periods/{period_id}/cycles")
    assert response.status_code == 200
    assert "15th" in response.text
    assert "Live template" in response.text
    assert "0 closed" in response.text
    assert "1,000.00" in response.text


def test_close_cycle_creates_a_dated_snapshot(client: TestClient) -> None:
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
            "name": "Rent",
            "amount": "100",
            "payout_period_id": period_id,
            "channel_id": a,
        },
    )

    response = client.post(f"/payout-periods/{period_id}/cycles")
    assert response.status_code == 200
    assert "1 closed" in response.text

    cycle_match = re.search(r"cycle_id=(\d+)", response.text)
    assert cycle_match is not None
    cycle_id = cycle_match.group(1)

    snapshot = client.get(f"/payout-periods/{period_id}/cycles", params={"cycle_id": cycle_id})
    assert snapshot.status_code == 200
    assert "Snapshot" in snapshot.text
    # A: 1000 income - 300 transferred out - 100 expense = 600
    assert "600.00" in snapshot.text
    # B: 300 transferred in = 300
    assert "300.00" in snapshot.text


def test_editing_live_transfer_after_close_does_not_change_the_snapshot(
    client: TestClient,
) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)

    # Created via crud directly rather than POST /transfers -- the transfer
    # edge's HTML only renders data-edge-id once both channels are placed on
    # the Cash Flow canvas, which is tangential to what this test covers.
    db = TestingSessionLocal()
    try:
        transfer = crud.create_transfer(
            db,
            schemas.TransferCreate(
                payout_period_id=int(period_id),
                from_channel_id=int(a),
                to_channel_id=int(b),
                amount=300,
            ),
            TEST_USER_ID,
        )
        transfer_id = transfer.id
    finally:
        db.close()

    closed = client.post(f"/payout-periods/{period_id}/cycles")
    cycle_match = re.search(r"cycle_id=(\d+)", closed.text)
    assert cycle_match is not None
    cycle_id = cycle_match.group(1)

    # Now edit the live transfer -- this is exactly the scenario #84 exists
    # to fix: editing this cycle's transfer amount used to silently
    # overwrite the only record that ever existed.
    # 450, not e.g. 700 -- picked so it doesn't coincidentally match any
    # other number in this test (1000 - 300 = 700 would collide with a
    # naive "700" edit and make a real bug look like a pass).
    client.patch(f"/transfers/{transfer_id}", data={"amount": "450"})

    snapshot = client.get(f"/payout-periods/{period_id}/cycles", params={"cycle_id": cycle_id})
    assert "-₱300.00" in snapshot.text  # snapshot still shows the old transfer amount
    assert "₱700.00" in snapshot.text  # and the balance computed from it (1000 - 300)
    assert "-₱450.00" not in snapshot.text
    assert "₱550.00" not in snapshot.text

    live = client.get(f"/payout-periods/{period_id}/cycles")
    assert "-₱450.00" in live.text  # live view reflects the edit
    assert "₱550.00" in live.text  # and the balance recomputed from it (1000 - 450)


def test_cycle_history_requires_ownership(client: TestClient) -> None:
    response = client.get("/payout-periods/999999/cycles")
    assert response.status_code == 404


def test_close_cycle_requires_ownership(client: TestClient) -> None:
    response = client.post("/payout-periods/999999/cycles")
    assert response.status_code == 404


def test_viewing_unknown_cycle_id_404s(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", "1000", channel_id)

    response = client.get(f"/payout-periods/{period_id}/cycles", params={"cycle_id": "999999"})
    assert response.status_code == 404


def test_history_link_appears_on_expenses_page(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", "1000", channel_id)

    response = client.get("/expenses")
    assert response.status_code == 200
    assert f"/payout-periods/{period_id}/cycles" in response.text


def test_multiple_closed_cycles_ordered_newest_first(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", "1000", channel_id)

    first = client.post(f"/payout-periods/{period_id}/cycles")
    first_id = re.search(r"cycle_id=(\d+)", first.text)
    assert first_id is not None

    client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "2000", "receiving_channel_id": channel_id},
    )
    second = client.post(f"/payout-periods/{period_id}/cycles")
    assert "2 closed" in second.text

    # Newest cycle chip should appear before the older one in the rail.
    second_id_match = re.search(r"cycle_id=(\d+)", second.text)
    assert second_id_match is not None
    second_id = second_id_match.group(1)
    assert second.text.index(f"cycle_id={second_id}") < second.text.index(
        f"cycle_id={first_id.group(1)}"
    )
