import re
import time

import pytest
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
    # Periods are listed in ascending display_order, so the just-created one
    # (highest display_order) is the last match once more than one exists.
    matches = re.findall(r"/payout-periods/(\d+)", response.text)
    assert matches
    return matches[-1]


def _place_channel(client: TestClient, period_id: str, channel_id: str) -> None:
    response = client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "0", "y": "0"},
    )
    assert response.status_code == 200


def test_create_update_delete_transfer(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

    create = client.post(
        "/transfers",
        data={
            "payout_period_id": period_id,
            "from_channel_id": a,
            "to_channel_id": b,
            "amount": "300",
        },
    )
    assert create.status_code == 200
    match = re.search(r'data-edge-id="transfer-(\d+)"', create.text)
    assert match is not None
    transfer_id = match.group(1)

    updated = client.patch(f"/transfers/{transfer_id}", data={"amount": "400"})
    assert updated.status_code == 200

    deleted = client.delete(f"/transfers/{transfer_id}")
    assert deleted.status_code == 200


def test_channel_balances_reflect_income_transfers_and_expenses(client: TestClient) -> None:
    """Worked example: A receives 1000 income, sends 300 to B.
    A also has a 100 expense, B has a 50 expense.
    Expected: A net = 1000 - 300 - 100 = 600. B net = 300 - 50 = 250.
    """
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

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
            "name": "A bill",
            "amount": "100",
            "payout_period_id": period_id,
            "channel_id": a,
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "B bill",
            "amount": "50",
            "payout_period_id": period_id,
            "channel_id": b,
        },
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert "600.00" in response.text
    assert "250.00" in response.text


def test_cashflow_canvas_shows_channel_nodes_with_balances(
    client: TestClient,
) -> None:
    """B has a 500 expense and no income/transfers yet, so its canvas node
    should show a -500.00 balance; A (the receiving channel) should show
    its untouched 1000 income.
    """
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "1000", a)
    _place_channel(client, period_id, a)
    _place_channel(client, period_id, b)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.get("/cashflow")
    assert response.status_code == 200
    assert f'data-node-id="channel-{a}"' in response.text
    assert f'data-node-id="channel-{b}"' in response.text
    assert "1,000.00" in response.text
    assert "-₱500.00" in response.text


def test_channel_balances_carry_forward_across_many_periods() -> None:
    """Regression test for #67 (exponential-time recursion in the balance
    calculation): builds 9 payout periods where each period's balance
    depends on carry-in from the one before it, then checks every period's
    `channel_balances()` and `cashflow_page_data()` output against an
    independent, hand-written step-by-step simulation. Also cross-checks
    `cashflow_page_data()`'s per-period `carry_in`/`balance_by_channel`
    against the single-period `channel_balances()` entry point, since the
    fix must keep both call paths in agreement."""
    db = TestingSessionLocal()
    try:
        channel_a = crud.create_channel(db, schemas.ChannelCreate(name="Channel A"), TEST_USER_ID)
        channel_b = crud.create_channel(db, schemas.ChannelCreate(name="Channel B"), TEST_USER_ID)

        period_count = 9
        periods = []
        incomes = []
        transfer_amounts = []
        expense_a_amounts = []
        expense_b_amount = 25.0  # constant, alongside the varying amounts below

        for i in range(1, period_count + 1):
            income = 1000.0 + i * 10
            period = crud.create_payout_period(
                db,
                schemas.PayoutPeriodCreate(
                    label=f"Period {i}",
                    income_amount=income,
                    receiving_channel_id=channel_a.id,
                ),
                TEST_USER_ID,
            )
            periods.append(period)
            incomes.append(income)

            transfer_amount = 150.0 + i * 5
            transfer_amounts.append(transfer_amount)
            crud.create_transfer(
                db,
                schemas.TransferCreate(
                    payout_period_id=period.id,
                    from_channel_id=channel_a.id,
                    to_channel_id=channel_b.id,
                    amount=transfer_amount,
                ),
                TEST_USER_ID,
            )

            expense_a = 40.0 + i
            expense_a_amounts.append(expense_a)
            crud.create_expense(
                db,
                schemas.ExpenseCreate(
                    name=f"A bill {i}",
                    amount=expense_a,
                    payout_period_id=period.id,
                    channel_id=channel_a.id,
                ),
                TEST_USER_ID,
            )
            crud.create_expense(
                db,
                schemas.ExpenseCreate(
                    name=f"B bill {i}",
                    amount=expense_b_amount,
                    payout_period_id=period.id,
                    channel_id=channel_b.id,
                ),
                TEST_USER_ID,
            )

        # Independent step-by-step simulation -- not calling any of crud's
        # carry-in logic -- that the balances below are checked against.
        carry_a = 0.0
        carry_b = 0.0
        expected: list[tuple[float, float]] = []
        for i in range(period_count):
            net_a = carry_a + incomes[i] - transfer_amounts[i] - expense_a_amounts[i]
            net_b = carry_b + transfer_amounts[i] - expense_b_amount
            expected.append((net_a, net_b))
            carry_a, carry_b = net_a, net_b

        for i, period in enumerate(periods):
            balances = {c.id: net for c, net in crud.channel_balances(db, period.id, TEST_USER_ID)}
            assert balances[channel_a.id] == pytest.approx(expected[i][0])
            assert balances[channel_b.id] == pytest.approx(expected[i][1])

        # cashflow_page_data must produce identical balances/carry-in for
        # every period as the single-period channel_balances() calls above --
        # both code paths now share the same O(n) internal computation.
        page_data = crud.cashflow_page_data(db, TEST_USER_ID)
        assert len(page_data["payout_data"]) == period_count
        for i, entry in enumerate(page_data["payout_data"]):
            balance_by_channel = entry["balance_by_channel"]
            assert balance_by_channel[channel_a.id] == pytest.approx(expected[i][0])
            assert balance_by_channel[channel_b.id] == pytest.approx(expected[i][1])
            if i == 0:
                assert entry["carry_in"] == {}
            else:
                assert entry["carry_in"][channel_a.id] == pytest.approx(expected[i - 1][0])
                assert entry["carry_in"][channel_b.id] == pytest.approx(expected[i - 1][1])
    finally:
        db.close()


def test_cashflow_page_data_completes_quickly_with_many_periods() -> None:
    """Perf-sanity regression test for #67: before the fix, computing N
    periods' balances was exponential (each period re-deriving every prior
    period from scratch), so ~20 periods would hang the request. Asserts the
    whole page's data assembly -- which used to redo this exponential work
    three times per period -- stays comfortably fast."""
    db = TestingSessionLocal()
    try:
        channel_a = crud.create_channel(db, schemas.ChannelCreate(name="Channel A"), TEST_USER_ID)
        channel_b = crud.create_channel(db, schemas.ChannelCreate(name="Channel B"), TEST_USER_ID)

        for i in range(1, 21):
            period = crud.create_payout_period(
                db,
                schemas.PayoutPeriodCreate(
                    label=f"Period {i}", income_amount=1000, receiving_channel_id=channel_a.id
                ),
                TEST_USER_ID,
            )
            crud.create_transfer(
                db,
                schemas.TransferCreate(
                    payout_period_id=period.id,
                    from_channel_id=channel_a.id,
                    to_channel_id=channel_b.id,
                    amount=200,
                ),
                TEST_USER_ID,
            )
            crud.create_expense(
                db,
                schemas.ExpenseCreate(
                    name=f"bill {i}", amount=30, payout_period_id=period.id, channel_id=channel_b.id
                ),
                TEST_USER_ID,
            )

        start = time.perf_counter()
        crud.cashflow_page_data(db, TEST_USER_ID)
        elapsed = time.perf_counter() - start
        assert (
            elapsed < 2.0
        ), f"cashflow_page_data took {elapsed:.2f}s for 20 periods -- likely exponential again"
    finally:
        db.close()
