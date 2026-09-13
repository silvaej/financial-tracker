import re
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app import crud, models, schemas
from app.crud import _most_recent_monthly_occurrence
from tests.conftest import TEST_USER_ID, TestingSessionLocal


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def test_create_cycle(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    response = client.post(
        "/cycles",
        data={
            "income_amount": "36100.46",
            "receiving_channel_id": channel_id,
            "payout_day": "15",
        },
    )
    assert response.status_code == 200
    assert "15th" in response.text
    assert "36100" in response.text


def test_create_cycle_with_no_channel(client: TestClient) -> None:
    response = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "30"},
    )
    assert response.status_code == 200
    assert "30th" in response.text


def test_create_cycle_rejects_missing_payout_day(client: TestClient) -> None:
    response = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 422


def test_create_cycle_rejects_out_of_range_payout_day(client: TestClient) -> None:
    for day in ("0", "32"):
        response = client.post(
            "/cycles",
            data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": day},
        )
        assert response.status_code == 422


def test_create_cycle_rejects_negative_income(client: TestClient) -> None:
    response = client.post(
        "/cycles",
        data={"income_amount": "-100", "receiving_channel_id": "", "payout_day": "15"},
    )
    assert response.status_code == 422


def test_update_cycle_rejects_negative_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    response = client.patch(
        f"/cycles/{cycle_id}",
        data={"income_amount": "-2000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    assert response.status_code == 422


def test_update_cycle_rejects_missing_payout_day(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    response = client.patch(
        f"/cycles/{cycle_id}",
        data={"income_amount": "1000", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 422


def test_update_cycle_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    response = client.patch(
        f"/cycles/{cycle_id}",
        data={"income_amount": "2000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    assert response.status_code == 200
    assert "2000" in response.text


def test_update_cycle_day(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    response = client.patch(
        f"/cycles/{cycle_id}",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "20"},
    )
    assert response.status_code == 200
    assert "20th" in response.text


def test_delete_empty_cycle_succeeds(client: TestClient) -> None:
    create = client.post(
        "/cycles",
        data={"income_amount": "0", "receiving_channel_id": "", "payout_day": "22"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)
    assert f'/cycles/{cycle_id}/history"' in create.text

    response = client.delete(f"/cycles/{cycle_id}")
    assert response.status_code == 200
    assert f'/cycles/{cycle_id}/history"' not in response.text


def test_delete_cycle_in_use_by_expense_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "5000",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
        },
    )

    response = client.delete(f"/cycles/{cycle_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


# --- Overdue-hint (payout_day) -----------------------------------------------
# Regression coverage for #134. `_most_recent_monthly_occurrence` is tested
# directly (pure function, no monkeypatching needed) for the calendar edge
# cases; the router-level tests use `today.day` itself as the payout_day so
# "is this overdue" is deterministic regardless of what day the suite runs on
# -- `_most_recent_monthly_occurrence` always returns a date <= today by
# construction, so payout_day == today.day always resolves to "occurred
# today", which is exactly the boundary case worth covering anyway.


def test_most_recent_monthly_occurrence_same_day() -> None:
    assert _most_recent_monthly_occurrence(15, date(2026, 6, 15)) == date(2026, 6, 15)


def test_most_recent_monthly_occurrence_earlier_this_month() -> None:
    assert _most_recent_monthly_occurrence(5, date(2026, 6, 20)) == date(2026, 6, 5)


def test_most_recent_monthly_occurrence_not_yet_this_month_falls_back_to_last_month() -> None:
    assert _most_recent_monthly_occurrence(25, date(2026, 6, 5)) == date(2026, 5, 25)


def test_most_recent_monthly_occurrence_clamps_to_shorter_month() -> None:
    # February 2026 (not a leap year) has 28 days -- day 31 clamps to the 28th.
    assert _most_recent_monthly_occurrence(31, date(2026, 2, 28)) == date(2026, 2, 28)
    # Asking on March 5th, before March's own 31st has occurred, falls back
    # to February's clamped occurrence, not March 31st.
    assert _most_recent_monthly_occurrence(31, date(2026, 3, 5)) == date(2026, 2, 28)


def test_most_recent_monthly_occurrence_wraps_year_boundary() -> None:
    assert _most_recent_monthly_occurrence(31, date(2026, 1, 5)) == date(2025, 12, 31)


def test_cycle_shows_overdue_dot_once_payday_has_passed(client: TestClient) -> None:
    today = datetime.now(UTC).date()
    response = client.post(
        "/cycles",
        data={
            "income_amount": "1000",
            "receiving_channel_id": "",
            "payout_day": str(today.day),
        },
    )
    assert response.status_code == 200
    assert "overdue-dot" in response.text


def test_closing_a_cycle_clears_the_overdue_dot(client: TestClient) -> None:
    today = datetime.now(UTC).date()
    create = client.post(
        "/cycles",
        data={
            "income_amount": "1000",
            "receiving_channel_id": "",
            "payout_day": str(today.day),
        },
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)
    assert "overdue-dot" in create.text

    close = client.post(f"/cycles/{cycle_id}/history")
    assert close.status_code == 200

    index = client.get("/expenses")
    assert "overdue-dot" not in index.text


def test_cycle_history_link_is_htmx_boosted(client: TestClient) -> None:
    """Regression test for #135: the link fell through to a full browser
    navigation instead of an htmx swap, since #page-content itself isn't
    boosted (only #rail/#tabbar/#more-sheet-overlay are) -- see
    app/templates/base.html."""
    create = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "15"},
    )
    match = re.search(r"/cycles/(\d+)", create.text)
    assert match is not None
    cycle_id = match.group(1)

    href = f'href="/cycles/{cycle_id}/history"'
    assert href in create.text
    link_tag = re.search(rf"<a[^>]*{re.escape(href)}[^>]*>", create.text, re.DOTALL)
    assert link_tag is not None
    assert 'hx-boost="true"' in link_tag.group()
    assert 'hx-target="#page-content"' in link_tag.group()
    assert 'hx-swap="innerHTML"' in link_tag.group()
    assert 'hx-push-url="true"' in link_tag.group()


# --- Cycle-count enforcement (#191) -------------------------------------------


def test_create_cycle_rejects_once_cap_is_reached(client: TestClient) -> None:
    # A fresh user's cycles_per_month defaults to 1.
    first = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "15"},
    )
    assert first.status_code == 200

    second = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "30"},
    )
    assert second.status_code == 409
    assert "cycle" in second.json()["detail"]


def test_update_cycles_per_month_allows_creating_more_cycles(client: TestClient) -> None:
    raise_cap = client.patch("/cycles/count", data={"cycles_per_month": "2"})
    assert raise_cap.status_code == 200
    assert re.search(r'name="cycles_per_month"[^>]*value="2"', raise_cap.text) is not None

    first = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "15"},
    )
    assert first.status_code == 200
    second = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "30"},
    )
    assert second.status_code == 200


def test_update_cycles_per_month_rejects_less_than_one(client: TestClient) -> None:
    response = client.patch("/cycles/count", data={"cycles_per_month": "0"})
    assert response.status_code == 422


def test_add_cycle_button_disabled_once_cap_is_reached(client: TestClient) -> None:
    response = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": "15"},
    )
    assert re.search(r'id="add-cycle-trigger"[^>]*disabled', response.text) is not None


def test_cycles_per_month_is_isolated_per_user() -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_user = crud.get_user(db, other_user_id)
        assert other_user is not None
        crud.update_cycles_per_month(db, other_user, 5)

        # The default test user's own cap (1) is unaffected by the other
        # user's cap (5).
        test_user = crud.get_user(db, TEST_USER_ID)
        assert test_user is not None
        assert test_user.cycles_per_month == 1

        crud.create_cycle(db, schemas.CycleCreate(payout_day=15), TEST_USER_ID)
        with pytest.raises(crud.CycleCapExceededError):
            crud.create_cycle(db, schemas.CycleCreate(payout_day=30), TEST_USER_ID)
    finally:
        db.close()
