import re

from fastapi.testclient import TestClient

from app import crud, schemas
from tests.conftest import TEST_USER_ID, TestingSessionLocal


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, label: str, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": label, "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def test_create_and_delete_expense(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Groceries",
            "amount": "150.75",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert create.status_code == 200
    assert "Groceries" in create.text
    assert "150.75" in create.text

    match = re.search(r"/expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    response = client.delete(f"/expenses/{expense_id}")
    assert response.status_code == 200
    assert "Groceries" not in response.text


def test_create_expense_with_due_day(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "12000",
            "payout_period_id": period_id,
            "channel_id": channel_id,
            "due_day": "5",
        },
    )
    assert create.status_code == 200
    assert "Rent" in create.text
    # The Due column should render the day-of-month next to the expense.
    assert re.search(r'data-label="Due">\s*5\s*<', create.text) is not None


def test_create_expense_without_due_day_leaves_it_blank(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Groceries",
            "amount": "150.75",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert create.status_code == 200
    assert "Groceries" in create.text


def test_create_expense_rejects_zero_or_negative_amount(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    for amount in ("0", "-50"):
        response = client.post(
            "/expenses",
            data={
                "name": "Groceries",
                "amount": amount,
                "payout_period_id": period_id,
                "channel_id": channel_id,
            },
        )
        assert response.status_code == 422


def test_validation_error_detail_is_a_plain_string_not_a_list(client: TestClient) -> None:
    # base.html's global htmx:responseError listener does
    # `alertMessage.textContent = data.detail` for every error path in this
    # app -- if `detail` were pydantic's default list-of-dicts shape instead
    # of a plain string, the user-facing alert would render "[object Object]".
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    response = client.post(
        "/expenses",
        data={
            "name": "Groceries",
            "amount": "-50",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "amount" in detail


def test_create_expense_rejects_whitespace_only_name(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    response = client.post(
        "/expenses",
        data={
            "name": "   ",
            "amount": "150.75",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert response.status_code == 422


def test_mark_expense_paid_and_unpaid(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "12000",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    match = re.search(r"/expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    # A brand-new expense starts unpaid.
    assert re.search(rf'expenses/{expense_id}/paid"[^>]*(?<!checked)>', create.text) is not None

    paid = client.patch(f"/expenses/{expense_id}/paid", data={"paid": "on"})
    assert paid.status_code == 200
    assert re.search(rf'expenses/{expense_id}/paid"[^>]*checked>', paid.text) is not None

    # Unchecking a checkbox omits it from the submitted form entirely --
    # mirrors real browser behavior (see the round_up_to_hundred checkbox
    # pattern elsewhere in this app).
    unpaid = client.patch(f"/expenses/{expense_id}/paid", data={})
    assert unpaid.status_code == 200
    assert re.search(rf'expenses/{expense_id}/paid"[^>]*checked>', unpaid.text) is None


def test_mark_expense_paid_requires_ownership(client: TestClient) -> None:
    response = client.patch("/expenses/999999/paid", data={"paid": "on"})
    assert response.status_code == 404


def test_pause_and_resume_expense(client: TestClient) -> None:
    """Regression test for #86: pausing an expense keeps the row (name still
    shown, "Paused" pill appears) instead of deleting it."""
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)

    create = client.post(
        "/expenses",
        data={
            "name": "Netflix",
            "amount": "549",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    match = re.search(r"/expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)
    assert "Paused" not in create.text

    paused = client.patch(f"/expenses/{expense_id}/active", data={"active": "false"})
    assert paused.status_code == 200
    assert "Netflix" in paused.text
    assert "Paused" in paused.text

    resumed = client.patch(f"/expenses/{expense_id}/active", data={"active": "true"})
    assert resumed.status_code == 200
    assert "Netflix" in resumed.text
    assert "Paused" not in resumed.text


def test_pause_expense_requires_ownership(client: TestClient) -> None:
    response = client.patch("/expenses/999999/active", data={"active": "false"})
    assert response.status_code == 404


def test_paused_expense_excluded_from_channel_balance() -> None:
    """A paused expense keeps its row (channel/amount/history intact) but no
    longer counts toward the period's balance calculation."""
    db = TestingSessionLocal()
    try:
        channel = crud.create_channel(db, schemas.ChannelCreate(name="BPI"), TEST_USER_ID)
        period = crud.create_payout_period(
            db,
            schemas.PayoutPeriodCreate(
                label="15th", income_amount=1000, receiving_channel_id=channel.id
            ),
            TEST_USER_ID,
        )
        expense = crud.create_expense(
            db,
            schemas.ExpenseCreate(
                name="Netflix", amount=549, payout_period_id=period.id, channel_id=channel.id
            ),
            TEST_USER_ID,
        )

        balances = {c.id: net for c, net in crud.channel_balances(db, period.id, TEST_USER_ID)}
        assert balances[channel.id] == 1000 - 549

        crud.set_expense_active(db, expense.id, TEST_USER_ID, False)
        balances = {c.id: net for c, net in crud.channel_balances(db, period.id, TEST_USER_ID)}
        assert balances[channel.id] == 1000

        crud.set_expense_active(db, expense.id, TEST_USER_ID, True)
        balances = {c.id: net for c, net in crud.channel_balances(db, period.id, TEST_USER_ID)}
        assert balances[channel.id] == 1000 - 549
    finally:
        db.close()


def test_expenses_filter_by_name(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, "15th", channel_id)
    client.post(
        "/expenses",
        data={
            "name": "Groceries",
            "amount": "150.75",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "Electricity",
            "amount": "800",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )

    unfiltered = client.get("/expenses", headers={"HX-Request": "true"})
    assert "Groceries" in unfiltered.text
    assert "Electricity" in unfiltered.text

    filtered = client.get("/expenses", params={"q": "groc"}, headers={"HX-Request": "true"})
    assert "Groceries" in filtered.text
    assert "Electricity" not in filtered.text

    no_match = client.get("/expenses", params={"q": "nonexistent"}, headers={"HX-Request": "true"})
    assert "Groceries" not in no_match.text
    assert "Electricity" not in no_match.text
    assert "0 items" in no_match.text
