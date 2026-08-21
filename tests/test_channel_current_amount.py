import re

from fastapi.testclient import TestClient

from app import crud, models, schemas
from tests.conftest import TEST_USER_ID, TestingSessionLocal


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, income: str, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": income, "receiving_channel_id": channel_id},
    )
    matches = re.findall(r"/payout-periods/(\d+)", response.text)
    assert matches
    return matches[-1]


def test_current_amount_defaults_to_zero_and_renders(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert "Actual balance" in response.text


def test_update_channel_sets_current_amount(client: TestClient) -> None:
    channel_id = _create_channel(client, "Maya Wallet")

    response = client.patch(
        f"/channels/{channel_id}",
        data={"name": "Maya Wallet", "color": "#8a8a8a", "current_amount": "500.25"},
    )
    assert response.status_code == 200
    assert "500.25" in response.text

    db = TestingSessionLocal()
    try:
        channel = db.get(models.Channel, int(channel_id))
        assert channel is not None
        assert float(channel.current_amount) == 500.25
    finally:
        db.close()


def test_current_amount_seeds_carry_in_for_first_period(client: TestClient) -> None:
    channel_id = _create_channel(client, "Maya Wallet")
    client.patch(
        f"/channels/{channel_id}",
        data={"name": "Maya Wallet", "color": "#8a8a8a", "current_amount": "500"},
    )
    period_id = _create_payout_period(client, "1000", channel_id)

    live = client.get(f"/payout-periods/{period_id}/cycles")
    assert live.status_code == 200
    # 500 (Actual baseline) + 1000 (this period's income) = 1500.
    assert "1,500.00" in live.text


def test_close_payout_cycle_increments_by_period_delta_not_full_net(client: TestClient) -> None:
    channel_id = _create_channel(client, "Maya Wallet")
    client.patch(
        f"/channels/{channel_id}",
        data={"name": "Maya Wallet", "color": "#8a8a8a", "current_amount": "500"},
    )
    period_id = _create_payout_period(client, "1000", channel_id)

    client.post(f"/payout-periods/{period_id}/cycles")

    db = TestingSessionLocal()
    try:
        channel = db.get(models.Channel, int(channel_id))
        assert channel is not None
        # delta = net(1500) - carry_in(500) = 1000, so current_amount = 500 + 1000 = 1500,
        # NOT the full net (1500) added on top of the existing 500 (which would be 2000).
        assert float(channel.current_amount) == 1500.0
    finally:
        db.close()

    # Closing again (same period, unchanged) re-derives carry-in from the
    # now-updated current_amount (1500), so the delta this time is another
    # 1000 -- this period is a recurring template, so a second close
    # legitimately represents receiving this income again, not a double-count
    # of the first close.
    client.post(f"/payout-periods/{period_id}/cycles")
    db = TestingSessionLocal()
    try:
        channel = db.get(models.Channel, int(channel_id))
        assert channel is not None
        assert float(channel.current_amount) == 2500.0
    finally:
        db.close()


def test_current_amount_edit_is_isolated_per_user() -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_channel = crud.create_channel(
            db, schemas.ChannelCreate(name="Someone Else's Wallet"), other_user_id
        )
        other_channel_id = other_channel.id

        result = crud.update_channel(
            db,
            other_channel_id,
            schemas.ChannelUpdate(name="Hijacked", color="#000000", current_amount=999),
            TEST_USER_ID,
        )
        assert result is None

        untouched = db.get(models.Channel, other_channel_id)
        assert untouched is not None
        assert untouched.name == "Someone Else's Wallet"
        assert float(untouched.current_amount) == 0.0
    finally:
        db.close()
