import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import crud, schemas
from app.auth import get_current_user, hash_password
from app.main import app
from tests.conftest import TestingSessionLocal


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, label: str) -> str:
    response = client.post("/payout-periods", data={"label": label, "income_amount": "0"})
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def _create_goal(client: TestClient, name: str, target: str) -> str:
    response = client.post("/goals", data={"name": name, "target": target, "months": "1"})
    match = re.search(r'/goals/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def test_create_goal_contribution_updates_goal_allocated(client: TestClient) -> None:
    channel_id = _create_channel(client, "Savings")
    period_id = _create_payout_period(client, "15th")
    goal_id = _create_goal(client, "Emergency Fund", "1000")

    response = client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": channel_id,
            "payout_period_id": period_id,
            "amount": "300",
        },
    )
    assert response.status_code == 200

    goals_page = client.get("/goals")
    assert "30%" in goals_page.text


def test_update_goal_contribution_recomputes_allocated(client: TestClient) -> None:
    channel_id = _create_channel(client, "Savings")
    period_id = _create_payout_period(client, "15th")
    goal_id = _create_goal(client, "Emergency Fund", "1000")

    create = client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": channel_id,
            "payout_period_id": period_id,
            "amount": "300",
        },
    )
    match = re.search(r'data-edge-id="goal-contribution-(\d+)"', create.text)
    assert match is not None
    contribution_id = match.group(1)

    client.patch(f"/goal-contributions/{contribution_id}", data={"amount": "600"})

    goals_page = client.get("/goals")
    assert "60%" in goals_page.text


def test_delete_goal_contribution_recomputes_allocated(client: TestClient) -> None:
    channel_id = _create_channel(client, "Savings")
    period_id = _create_payout_period(client, "15th")
    goal_id = _create_goal(client, "Emergency Fund", "1000")

    create = client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": channel_id,
            "payout_period_id": period_id,
            "amount": "300",
        },
    )
    match = re.search(r'data-edge-id="goal-contribution-(\d+)"', create.text)
    assert match is not None
    contribution_id = match.group(1)

    client.delete(f"/goal-contributions/{contribution_id}")

    goals_page = client.get("/goals")
    assert "0%" in goals_page.text


def test_goal_can_receive_contributions_from_two_channels_same_period(
    client: TestClient,
) -> None:
    channel_a = _create_channel(client, "Bank A")
    channel_b = _create_channel(client, "Bank B")
    period_id = _create_payout_period(client, "15th")
    goal_id = _create_goal(client, "Emergency Fund", "1000")

    client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": channel_a,
            "payout_period_id": period_id,
            "amount": "300",
        },
    )
    client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id,
            "channel_id": channel_b,
            "payout_period_id": period_id,
            "amount": "200",
        },
    )

    goals_page = client.get("/goals")
    assert "50%" in goals_page.text


@pytest.fixture
def real_client() -> Generator[TestClient, None, None]:
    original = app.dependency_overrides.pop(get_current_user, None)
    yield TestClient(app)
    if original is not None:
        app.dependency_overrides[get_current_user] = original


def _create_user(email: str, password: str) -> int:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, email, hash_password(password))
        return user.id
    finally:
        db.close()


def test_create_goal_contribution_requires_owned_goal(real_client: TestClient) -> None:
    alice_id = _create_user("alice@example.com", "alice-pass")
    _create_user("bob@example.com", "bob-pass")

    db = TestingSessionLocal()
    try:
        alice_channel = crud.create_channel(db, schemas.ChannelCreate(name="Alice Bank"), alice_id)
        alice_period = crud.create_payout_period(
            db, schemas.PayoutPeriodCreate(label="15th"), alice_id
        )
        alice_goal = crud.create_goal(
            db, schemas.GoalCreate(name="Alice Goal", target=1000, months=1), alice_id
        )
        channel_id, period_id, goal_id = alice_channel.id, alice_period.id, alice_goal.id
    finally:
        db.close()

    real_client.post("/login", data={"email": "bob@example.com", "password": "bob-pass"})
    response = real_client.post(
        "/goal-contributions",
        data={
            "goal_id": str(goal_id),
            "channel_id": str(channel_id),
            "payout_period_id": str(period_id),
            "amount": "100",
        },
    )
    assert response.status_code == 404
