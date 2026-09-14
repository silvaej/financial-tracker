import re
from datetime import date

from fastapi.testclient import TestClient

from app import crud, models, schemas
from tests.conftest import TEST_USER_ID, TestingSessionLocal


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_cycle(client: TestClient, payout_day: int, channel_id: str) -> str:
    response = client.post(
        "/cycles",
        data={
            "income_amount": "1000",
            "receiving_channel_id": channel_id,
            "payout_day": str(payout_day),
        },
    )
    matches = re.findall(r"/cycles/(\d+)", response.text)
    assert matches
    return matches[-1]


def test_create_and_delete_one_time_expense(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)

    create = client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    assert create.status_code == 200
    assert "Aircon Repair" in create.text
    assert "3,500.00" in create.text
    assert "Sep 10" in create.text

    match = re.search(r"/one-time-expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    response = client.delete(f"/one-time-expenses/{expense_id}")
    assert response.status_code == 200
    assert "Aircon Repair" not in response.text


def test_create_one_time_expense_rejects_zero_or_negative_amount(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)

    for amount in ("0", "-50"):
        response = client.post(
            "/one-time-expenses",
            data={
                "name": "Gift",
                "amount": amount,
                "cycle_id": cycle_id,
                "channel_id": channel_id,
                "date": "2026-09-10",
            },
        )
        assert response.status_code == 422


def test_create_one_time_expense_rejects_whitespace_only_name(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)

    response = client.post(
        "/one-time-expenses",
        data={
            "name": "   ",
            "amount": "500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    assert response.status_code == 422


def test_update_one_time_expense(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    other_channel_id = _create_channel(client, "GCash")
    client.patch("/cycles/count", data={"cycles_per_month": "2"})
    cycle_id = _create_cycle(client, 15, channel_id)
    other_cycle_id = _create_cycle(client, 30, channel_id)

    create = client.post(
        "/one-time-expenses",
        data={
            "name": "Vet Visit",
            "amount": "1500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    match = re.search(r"/one-time-expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    updated = client.patch(
        f"/one-time-expenses/{expense_id}",
        data={
            "name": "Vet Visit (updated)",
            "amount": "2000",
            "cycle_id": other_cycle_id,
            "channel_id": other_channel_id,
            "date": "2026-09-22",
        },
    )
    assert updated.status_code == 200
    assert "Vet Visit (updated)" in updated.text
    assert "2,000.00" in updated.text
    assert "Sep 22" in updated.text


def test_update_one_time_expense_requires_owned_fks(client: TestClient) -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_channel = crud.create_channel(
            db, schemas.ChannelCreate(name="Someone Else's Wallet"), other_user_id
        )
        other_channel_id = str(other_channel.id)
    finally:
        db.close()

    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    create = client.post(
        "/one-time-expenses",
        data={
            "name": "Vet Visit",
            "amount": "1500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    match = re.search(r"/one-time-expenses/(\d+)", create.text)
    assert match is not None
    expense_id = match.group(1)

    response = client.patch(
        f"/one-time-expenses/{expense_id}",
        data={
            "name": "Vet Visit",
            "amount": "1500",
            "cycle_id": cycle_id,
            "channel_id": other_channel_id,
            "date": "2026-09-10",
        },
    )
    assert response.status_code == 404


def test_one_time_expense_edit_is_isolated_per_user() -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_channel = crud.create_channel(
            db, schemas.ChannelCreate(name="Someone Else's Wallet"), other_user_id
        )
        other_cycle = crud.create_cycle(
            db,
            schemas.CycleCreate(
                payout_day=15, income_amount=1000, receiving_channel_id=other_channel.id
            ),
            other_user_id,
        )
        other_expense = crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name="Someone else's spend",
                amount=500,
                cycle_id=other_cycle.id,
                channel_id=other_channel.id,
                date=date(2026, 9, 10),
            ),
            other_user_id,
        )

        my_channel = crud.create_channel(db, schemas.ChannelCreate(name="Mine"), TEST_USER_ID)
        my_cycle = crud.create_cycle(
            db,
            schemas.CycleCreate(
                payout_day=30, income_amount=500, receiving_channel_id=my_channel.id
            ),
            TEST_USER_ID,
        )

        result = crud.update_one_time_expense(
            db,
            other_expense.id,
            schemas.OneTimeExpenseUpdate(
                name="Hijacked",
                amount=1,
                cycle_id=my_cycle.id,
                channel_id=my_channel.id,
                date=date(2026, 9, 10),
            ),
            TEST_USER_ID,
        )
        assert result is None

        untouched = db.get(models.OneTimeExpense, other_expense.id)
        assert untouched is not None
        assert untouched.name == "Someone else's spend"
        assert float(untouched.amount) == 500.0
    finally:
        db.close()


def test_delete_one_time_expense_requires_ownership() -> None:
    """delete_one_time_expense is a silent no-op for a row that doesn't
    belong to the acting user -- matches delete_expense/_delete_owned's
    established behavior elsewhere in this app."""
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_channel = crud.create_channel(
            db, schemas.ChannelCreate(name="Someone Else's Wallet"), other_user_id
        )
        other_cycle = crud.create_cycle(
            db,
            schemas.CycleCreate(
                payout_day=15, income_amount=1000, receiving_channel_id=other_channel.id
            ),
            other_user_id,
        )
        other_expense = crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name="Someone else's spend",
                amount=500,
                cycle_id=other_cycle.id,
                channel_id=other_channel.id,
                date=date(2026, 9, 10),
            ),
            other_user_id,
        )

        crud.delete_one_time_expense(db, other_expense.id, TEST_USER_ID)

        untouched = db.get(models.OneTimeExpense, other_expense.id)
        assert untouched is not None
    finally:
        db.close()


def test_clear_all_wipes_every_one_time_expense(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    client.post(
        "/one-time-expenses",
        data={
            "name": "Vet Visit",
            "amount": "1500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-18",
        },
    )

    response = client.post("/one-time-expenses/clear")
    assert response.status_code == 200
    assert "Aircon Repair" not in response.text
    assert "Vet Visit" not in response.text
    assert "0 items" in response.text


def test_clear_all_only_affects_the_acting_user() -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_channel = crud.create_channel(
            db, schemas.ChannelCreate(name="Someone Else's Wallet"), other_user_id
        )
        other_cycle = crud.create_cycle(
            db,
            schemas.CycleCreate(
                payout_day=15, income_amount=1000, receiving_channel_id=other_channel.id
            ),
            other_user_id,
        )
        other_expense = crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name="Someone else's spend",
                amount=500,
                cycle_id=other_cycle.id,
                channel_id=other_channel.id,
                date=date(2026, 9, 10),
            ),
            other_user_id,
        )

        crud.clear_one_time_expenses(db, TEST_USER_ID)

        untouched = db.get(models.OneTimeExpense, other_expense.id)
        assert untouched is not None
    finally:
        db.close()


def test_one_time_expense_subtracted_from_channel_balance() -> None:
    """Ties into the same balance math as a recurring Expense row -- see
    crud._all_channel_balances."""
    db = TestingSessionLocal()
    try:
        channel = crud.create_channel(db, schemas.ChannelCreate(name="BPI"), TEST_USER_ID)
        cycle = crud.create_cycle(
            db,
            schemas.CycleCreate(payout_day=15, income_amount=1000, receiving_channel_id=channel.id),
            TEST_USER_ID,
        )
        crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name="Aircon Repair",
                amount=350,
                cycle_id=cycle.id,
                channel_id=channel.id,
                date=date(2026, 9, 10),
            ),
            TEST_USER_ID,
        )

        balances = {c.id: net for c, net in crud.channel_balances(db, cycle.id, TEST_USER_ID)}
        assert balances[channel.id] == 1000 - 350
    finally:
        db.close()


def test_delete_channel_in_use_by_one_time_expense_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )

    response = client.delete(f"/channels/{channel_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def test_delete_cycle_in_use_by_one_time_expense_is_rejected(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )

    response = client.delete(f"/cycles/{cycle_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def test_delete_category_in_use_by_one_time_expense_is_rejected(client: TestClient) -> None:
    category_response = client.post(
        "/expense-categories", data={"name": "Repairs", "color": "#8a8a8a"}
    )
    match = re.search(
        r'value="Repairs">.*?/expense-categories/(\d+)"', category_response.text, re.DOTALL
    )
    assert match is not None
    category_id = match.group(1)

    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "category_id": category_id,
            "date": "2026-09-10",
        },
    )

    response = client.delete(f"/expense-categories/{category_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def _clear_all_button(html: str) -> str:
    match = re.search(r'"/one-time-expenses/clear"[\s\S]*?</button>', html)
    assert match is not None
    return match.group(0)


def test_clear_all_button_disabled_when_empty_enabled_once_populated(
    client: TestClient,
) -> None:
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)

    empty_page = client.get("/expenses", headers={"HX-Request": "true"})
    assert "disabled" in _clear_all_button(empty_page.text)

    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    with_item = client.get("/expenses", headers={"HX-Request": "true"})
    assert "disabled" not in _clear_all_button(with_item.text)


def test_one_time_expenses_filter_by_name(client: TestClient) -> None:
    """Regression test for #216: the one-time expenses table had no name
    filter, unlike the recurring expenses table right above it."""
    channel_id = _create_channel(client, "BPI")
    cycle_id = _create_cycle(client, 15, channel_id)
    client.post(
        "/one-time-expenses",
        data={
            "name": "Vet Visit",
            "amount": "1500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )
    client.post(
        "/one-time-expenses",
        data={
            "name": "Aircon Repair",
            "amount": "3500",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "date": "2026-09-10",
        },
    )

    unfiltered = client.get("/one-time-expenses", headers={"HX-Request": "true"})
    assert "Vet Visit" in unfiltered.text
    assert "Aircon Repair" in unfiltered.text

    filtered = client.get("/one-time-expenses", params={"q": "vet"}, headers={"HX-Request": "true"})
    assert "Vet Visit" in filtered.text
    assert "Aircon Repair" not in filtered.text
