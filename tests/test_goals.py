import re

from fastapi.testclient import TestClient

from app import crud, models


def test_create_goal_appears_on_page(client: TestClient) -> None:
    response = client.post(
        "/goals", data={"name": "CAR DP", "target": "100000", "allocated": "0", "months": "6"}
    )
    assert response.status_code == 200
    assert "CAR DP" in response.text


def test_update_goal_renames_and_changes_amounts(client: TestClient) -> None:
    create = client.post(
        "/goals",
        data={"name": "Old Name", "target": "1000", "allocated": "0", "months": "1"},
    )
    match = re.search(r'/goals/(\d+)"', create.text)
    assert match is not None
    goal_id = match.group(1)

    response = client.patch(
        f"/goals/{goal_id}",
        data={"name": "New Name", "target": "2000", "allocated": "500", "months": "4"},
    )
    assert response.status_code == 200
    assert "New Name" in response.text
    assert "Old Name" not in response.text


def test_delete_goal(client: TestClient) -> None:
    create = client.post(
        "/goals", data={"name": "Temp Goal", "target": "1000", "allocated": "0", "months": "1"}
    )
    match = re.search(r'/goals/(\d+)"', create.text)
    assert match is not None
    goal_id = match.group(1)

    response = client.delete(f"/goals/{goal_id}")
    assert response.status_code == 200
    assert "Temp Goal" not in response.text


def test_goals_empty_state(client: TestClient) -> None:
    response = client.get("/goals")
    assert response.status_code == 200
    assert "No goals yet" in response.text


def test_goal_progress_percentage_reflects_allocated_over_target(client: TestClient) -> None:
    response = client.post(
        "/goals",
        data={"name": "Emergency Fund", "target": "1000", "allocated": "250", "months": "12"},
    )
    assert response.status_code == 200
    assert "25%" in response.text


def test_goal_progress_caps_at_100_when_overallocated(client: TestClient) -> None:
    response = client.post(
        "/goals", data={"name": "Overfunded", "target": "1000", "allocated": "1500", "months": "1"}
    )
    assert response.status_code == 200
    assert "100%" in response.text


def test_goal_progress_matches_spreadsheet_car_dp() -> None:
    goal = models.Goal(name="CAR DP", target=100000, allocated=0, months=6)
    progress = crud.goal_progress(goal)
    assert progress["monthly_needed"] == 100000 / 6
    assert progress["pct"] == 0.0
    assert progress["remaining"] == 100000


def test_goal_progress_matches_spreadsheet_emergency_fund() -> None:
    goal = models.Goal(
        name="1 month worth emergency fund", target=50000, allocated=9182.81, months=12
    )
    progress = crud.goal_progress(goal)
    assert round(progress["pct"], 2) == round(0.1836562 * 100, 2)
    assert round(progress["remaining"], 2) == 40817.19
