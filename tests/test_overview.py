import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str) -> str:
    response = client.post("/channels", data={"name": name, "color": "#8a8a8a"})
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


def test_overview_empty_state(client: TestClient) -> None:
    response = client.get("/overview")
    assert response.status_code == 200
    assert "No goals yet" in response.text
    assert "No credit lines yet" in response.text
    assert "Upcoming" not in response.text


def test_overview_upcoming_expenses_banner(client: TestClient) -> None:
    channel = client.post("/channels", data={"name": "Payroll", "color": "#8a8a8a"})
    channel_id = re.search(r'/channels/(\d+)"', channel.text)
    assert channel_id is not None
    channel_id_str = channel_id.group(1)

    period = client.post("/payout-periods", data={"label": "15th", "income_amount": "32000"})
    period_id = re.search(r"/payout-periods/(\d+)", period.text)
    assert period_id is not None
    period_id_str = period_id.group(1)

    client.post(
        "/expenses",
        data={
            "name": "Meralco",
            "amount": "2500.50",
            "payout_period_id": period_id_str,
            "channel_id": channel_id_str,
        },
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "Upcoming — 15th" in response.text
    assert "Meralco" in response.text
    assert "2,500.50" in response.text


def test_overview_upcoming_expenses_sorted_by_due_day(client: TestClient) -> None:
    channel_id = _create_channel(client, "Payroll")
    period_id = _create_payout_period(client, "15th", "32000", channel_id)

    client.post(
        "/expenses",
        data={
            "name": "No due day",
            "amount": "100",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "Due later",
            "amount": "200",
            "payout_period_id": period_id,
            "channel_id": channel_id,
            "due_day": "20",
        },
    )
    client.post(
        "/expenses",
        data={
            "name": "Due soonest",
            "amount": "300",
            "payout_period_id": period_id,
            "channel_id": channel_id,
            "due_day": "5",
        },
    )

    response = client.get("/overview")
    assert response.status_code == 200
    text = response.text
    # Expenses without a due_day should sort after ones with one, and among
    # those with a due_day, the soonest (smallest) should come first.
    pos_soonest = text.index("Due soonest")
    pos_later = text.index("Due later")
    pos_no_due_day = text.index("No due day")
    assert pos_soonest < pos_later < pos_no_due_day


def test_overview_no_upcoming_banner_without_payout_periods(client: TestClient) -> None:
    client.post("/assets", data={"name": "Some Asset", "amount": "100"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "Upcoming" not in response.text


def test_overview_kpi_totals(client: TestClient) -> None:
    client.post("/assets", data={"name": "BPI IMI", "amount": "11210.80"})
    client.post("/assets", data={"name": "Maya TD", "amount": "5053.43"})
    client.post(
        "/credit", data={"name": "BPI Blue Mastercard", "limit": "196000", "used": "12367.39"}
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "16,264.23" in response.text  # total assets
    assert "12,367.39" in response.text  # total liabilities
    assert "3,896.84" in response.text  # net worth


def test_overview_net_worth_negative_uses_neg_class(client: TestClient) -> None:
    client.post("/assets", data={"name": "Small Asset", "amount": "100"})
    client.post("/credit", data={"name": "Big Card", "limit": "10000", "used": "5000"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "card-value-neg" in response.text


def test_overview_shows_funded_pill_for_completed_goal(client: TestClient) -> None:
    channel = client.post("/channels", data={"name": "Savings", "color": "#8a8a8a"})
    channel_id = re.search(r'/channels/(\d+)"', channel.text)
    assert channel_id is not None
    channel_id_str = channel_id.group(1)

    period = client.post("/payout-periods", data={"label": "15th", "income_amount": "0"})
    period_id = re.search(r"/payout-periods/(\d+)", period.text)
    assert period_id is not None
    period_id_str = period_id.group(1)

    goal = client.post(
        "/goals",
        data={
            "name": "Fully Funded",
            "target": "1000",
            "months": "1",
            "channel_id": channel_id_str,
        },
    )
    goal_id = re.search(r'/goals/(\d+)"', goal.text)
    assert goal_id is not None
    goal_id_str = goal_id.group(1)

    client.post(
        "/goal-contributions",
        data={
            "goal_id": goal_id_str,
            "channel_id": channel_id_str,
            "payout_period_id": period_id_str,
            "amount": "1000",
        },
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "pill-gold" in response.text
    assert "Funded" in response.text


def test_overview_does_not_show_funded_pill_for_incomplete_goal(client: TestClient) -> None:
    client.post("/goals", data={"name": "In Progress", "target": "1000", "months": "1"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "pill-gold" not in response.text


def test_overview_shows_warn_pill_for_near_limit_credit(client: TestClient) -> None:
    client.post("/credit", data={"name": "Near Limit", "limit": "1000", "used": "850"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "warn-amber" in response.text
    assert "Near limit" in response.text


def test_overview_shows_warn_pill_for_over_limit_credit(client: TestClient) -> None:
    client.post("/credit", data={"name": "Over Limit", "limit": "1000", "used": "1200"})

    response = client.get("/overview")
    assert response.status_code == 200
    assert "warn-red" in response.text
    assert "Over limit" in response.text


def test_overview_shows_no_cash_flow_warnings_section_when_none(client: TestClient) -> None:
    response = client.get("/overview")
    assert response.status_code == 200
    assert "Cash flow warnings" not in response.text


def test_overview_surfaces_unfunded_channel_warning(client: TestClient) -> None:
    a = _create_channel(client, "Channel A")
    b = _create_channel(client, "Channel B")
    period_id = _create_payout_period(client, "15th", "0", a)

    client.post(
        "/expenses",
        data={"name": "B bill", "amount": "500", "payout_period_id": period_id, "channel_id": b},
    )

    response = client.get("/overview")
    assert response.status_code == 200
    assert "Cash flow warnings" in response.text
    assert "Channel B goes negative on the 15th" in response.text
    assert "warn-red" in response.text


def test_unknown_section_still_404s(client: TestClient) -> None:
    response = client.get("/nonsense")
    assert response.status_code == 404


def test_summary_cards_explain_what_they_mean(client: TestClient) -> None:
    """Regression test for #136: the stat cards had no explanation of what
    feeds them (e.g. "Total liabilities" only counts CreditLine.used, not
    Goals or Expenses -- easy to assume otherwise)."""
    response = client.get("/overview")
    assert response.status_code == 200
    assert 'title="Sum of everything on the Assets page' in response.text
    assert "title=\"Sum of what's currently used on your Credit lines" in response.text
    assert 'title="Total assets minus total liabilities' in response.text
