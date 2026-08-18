import re
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.crud import _most_recent_monthly_occurrence


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def test_create_payout_period(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "36100.46", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 200
    assert "15th" in response.text
    assert "36100" in response.text


def test_create_payout_period_with_no_channel(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "30th", "income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 200
    assert "30th" in response.text


def test_create_payout_period_rejects_whitespace_only_label(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "   ", "income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 422


def test_create_payout_period_rejects_negative_income(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "-100", "receiving_channel_id": ""},
    )
    assert response.status_code == 422


def test_update_payout_period_rejects_negative_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "-2000", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 422


def test_update_payout_period_income(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "2000", "receiving_channel_id": channel_id},
    )
    assert response.status_code == 200
    assert "2000" in response.text


def test_delete_empty_payout_period_succeeds(client: TestClient) -> None:
    create = client.post(
        "/payout-periods",
        data={"label": "Empty Period", "income_amount": "0", "receiving_channel_id": ""},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.delete(f"/payout-periods/{period_id}")
    assert response.status_code == 200
    assert "Empty Period" not in response.text


def test_delete_payout_period_in_use_by_expense_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "5000",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )

    response = client.delete(f"/payout-periods/{period_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def test_create_payout_period_with_payout_day(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={
            "label": "15th",
            "income_amount": "1000",
            "receiving_channel_id": "",
            "payout_day": "15",
        },
    )
    assert response.status_code == 200
    assert re.search(r'name="payout_day"[^>]*value="15"', response.text)


def test_update_payout_period_clears_payout_day(client: TestClient) -> None:
    create = client.post(
        "/payout-periods",
        data={
            "label": "15th",
            "income_amount": "1000",
            "receiving_channel_id": "",
            "payout_day": "15",
        },
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    response = client.patch(
        f"/payout-periods/{period_id}",
        data={"income_amount": "1000", "receiving_channel_id": "", "payout_day": ""},
    )
    assert response.status_code == 200
    assert not re.search(r'name="payout_day"[^>]*value="\d', response.text)


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


def test_payout_period_with_no_payout_day_never_shows_overdue_dot(client: TestClient) -> None:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": ""},
    )
    assert response.status_code == 200
    assert "overdue-dot" not in response.text


def test_payout_period_shows_overdue_dot_once_payday_has_passed(client: TestClient) -> None:
    today = datetime.now(UTC).date()
    response = client.post(
        "/payout-periods",
        data={
            "label": "Today's payday",
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
        "/payout-periods",
        data={
            "label": "Today's payday",
            "income_amount": "1000",
            "receiving_channel_id": "",
            "payout_day": str(today.day),
        },
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)
    assert "overdue-dot" in create.text

    close = client.post(f"/payout-periods/{period_id}/cycles")
    assert close.status_code == 200

    index = client.get("/expenses")
    assert "overdue-dot" not in index.text


def test_cycle_history_link_is_htmx_boosted(client: TestClient) -> None:
    """Regression test for #135: the link fell through to a full browser
    navigation instead of an htmx swap, since #page-content itself isn't
    boosted (only #rail/#tabbar/#more-sheet-overlay are) -- see
    app/templates/base.html."""
    create = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": ""},
    )
    match = re.search(r"/payout-periods/(\d+)", create.text)
    assert match is not None
    period_id = match.group(1)

    href = f'href="/payout-periods/{period_id}/cycles"'
    assert href in create.text
    link_tag = re.search(rf"<a[^>]*{re.escape(href)}[^>]*>", create.text, re.DOTALL)
    assert link_tag is not None
    assert 'hx-boost="true"' in link_tag.group()
    assert 'hx-target="#page-content"' in link_tag.group()
    assert 'hx-swap="innerHTML"' in link_tag.group()
    assert 'hx-push-url="true"' in link_tag.group()
