import re

from fastapi.testclient import TestClient

from app import crud, models, schemas
from tests.conftest import TEST_USER_ID, TestingSessionLocal


def _create_category(client: TestClient, name: str, color: str = "#8a8a8a") -> str:
    response = client.post("/expense-categories", data={"name": name, "color": color})
    match = re.search(
        rf'value="{re.escape(name)}">.*?/expense-categories/(\d+)"', response.text, re.DOTALL
    )
    assert match is not None
    return match.group(1)


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', response.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def _create_cycle(client: TestClient, channel_id: str) -> str:
    response = client.post(
        "/cycles",
        data={"income_amount": "1000", "receiving_channel_id": channel_id, "payout_day": "15"},
    )
    matches = re.findall(r"/cycles/(\d+)", response.text)
    assert matches
    return matches[-1]


def test_create_category_appears_on_page(client: TestClient) -> None:
    response = client.post("/expense-categories", data={"name": "Utilities", "color": "#B8122B"})
    assert response.status_code == 200
    assert "Utilities" in response.text


def test_create_category_rejects_whitespace_only_name(client: TestClient) -> None:
    response = client.post("/expense-categories", data={"name": "   ", "color": "#8a8a8a"})
    assert response.status_code == 422


def test_update_category_renames_it(client: TestClient) -> None:
    category_id = _create_category(client, "Subscriptions")

    response = client.patch(
        f"/expense-categories/{category_id}", data={"name": "Streaming", "color": "#8a8a8a"}
    )
    assert response.status_code == 200
    assert "Streaming" in response.text
    assert "Subscriptions" not in response.text


def test_delete_category(client: TestClient) -> None:
    category_id = _create_category(client, "Temp Category")

    response = client.delete(f"/expense-categories/{category_id}")
    assert response.status_code == 200
    assert "Temp Category" not in response.text


def test_delete_category_in_use_by_expense_is_rejected(client: TestClient) -> None:
    category_id = _create_category(client, "Rent and Utilities")
    channel_id = _create_channel(client, "BPI Payroll")
    cycle_id = _create_cycle(client, channel_id)
    client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "12000",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "category_id": category_id,
        },
    )

    response = client.delete(f"/expense-categories/{category_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def test_create_expense_with_category_shows_it_on_the_table(client: TestClient) -> None:
    category_id = _create_category(client, "Utilities")
    channel_id = _create_channel(client, "BPI Payroll")
    cycle_id = _create_cycle(client, channel_id)

    response = client.post(
        "/expenses",
        data={
            "name": "Electricity",
            "amount": "2200",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "category_id": category_id,
        },
    )
    assert response.status_code == 200
    assert "Utilities" in response.text


def test_create_expense_without_category_still_works(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI Payroll")
    cycle_id = _create_cycle(client, channel_id)

    response = client.post(
        "/expenses",
        data={
            "name": "Internet",
            "amount": "1699",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
        },
    )
    assert response.status_code == 200
    assert "Internet" in response.text


def test_create_expense_rejects_unowned_category(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI Payroll")
    cycle_id = _create_cycle(client, channel_id)

    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_category = crud.create_expense_category(
            db, schemas.ExpenseCategoryCreate(name="Someone Else's Category"), other_user_id
        )
        other_category_id = other_category.id
    finally:
        db.close()

    response = client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "12000",
            "cycle_id": cycle_id,
            "channel_id": channel_id,
            "category_id": str(other_category_id),
        },
    )
    assert response.status_code == 404


def test_category_edit_is_isolated_per_user() -> None:
    db = TestingSessionLocal()
    try:
        other_user_id = TEST_USER_ID + 1
        db.add(models.User(id=other_user_id, email="other@example.com"))
        db.commit()
        other_category = crud.create_expense_category(
            db, schemas.ExpenseCategoryCreate(name="Someone Else's Category"), other_user_id
        )
        other_category_id = other_category.id

        result = crud.update_expense_category(
            db,
            other_category_id,
            schemas.ExpenseCategoryUpdate(name="Hijacked", color="#000000"),
            TEST_USER_ID,
        )
        assert result is None

        untouched = db.get(models.ExpenseCategory, other_category_id)
        assert untouched is not None
        assert untouched.name == "Someone Else's Category"
    finally:
        db.close()


def test_categories_filter_by_name_keeps_dropdowns_intact(client: TestClient) -> None:
    """Regression test for #219: search narrows the Categories table itself,
    but the same categories list also populates every category_id <select>
    dropdown on the Expenses page -- those must stay unfiltered."""
    housing_id = _create_category(client, "Housing")
    repairs_id = _create_category(client, "Repairs")

    filtered = client.get(
        "/expense-categories", params={"q": "hous"}, headers={"HX-Request": "true"}
    )
    assert filtered.status_code == 200
    assert f"view-category-{housing_id}" in filtered.text
    assert f"view-category-{repairs_id}" not in filtered.text
    assert f'value="{repairs_id}"' in filtered.text
