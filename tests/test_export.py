import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str, color: str = "#8a8a8a") -> str:
    response = client.post("/channels", data={"name": name, "color": color})
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


def test_export_channels_csv(client: TestClient) -> None:
    _create_channel(client, "BPI", "#B8122B")

    response = client.get("/export/channels.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="channels.csv"'
    assert "Name,Color,Type" in response.text
    assert "BPI,#B8122B" in response.text


def test_export_payout_periods_csv(client: TestClient) -> None:
    channel_id = _create_channel(client, "GCash", "#0072CE")
    _create_payout_period(client, "15th", "1000", channel_id)

    response = client.get("/export/payout-periods.csv")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == ('attachment; filename="payout-periods.csv"')
    assert "Label,Income Amount,Receiving Channel" in response.text
    assert "15th,1000.00,GCash" in response.text


def test_export_expenses_csv(client: TestClient) -> None:
    channel_id = _create_channel(client, "BDO", "#003DA5")
    period_id = _create_payout_period(client, "30th", "2000", channel_id)

    client.post(
        "/expenses",
        data={
            "name": "Meralco",
            "amount": "1500",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )

    response = client.get("/export/expenses.csv")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="expenses.csv"'
    assert "Name,Amount,Payout Period,Channel" in response.text
    assert "Meralco,1500.00,30th,BDO" in response.text


def test_export_transfers_csv(client: TestClient) -> None:
    from_id = _create_channel(client, "Maya", "#0FA968")
    to_id = _create_channel(client, "Savings", "#8a8a8a")
    period_id = _create_payout_period(client, "15th", "1000", from_id)

    client.post(
        "/transfers",
        data={
            "payout_period_id": period_id,
            "from_channel_id": from_id,
            "to_channel_id": to_id,
            "amount": "300",
        },
    )

    response = client.get("/export/transfers.csv")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="transfers.csv"'
    assert "Payout Period,From Channel,To Channel,Amount" in response.text
    assert "15th,Maya,Savings,300.00" in response.text


def test_export_empty_data_returns_header_only(client: TestClient) -> None:
    response = client.get("/export/channels.csv")

    assert response.status_code == 200
    assert response.text.strip() == "Name,Color,Type"


def test_export_channels_csv_sanitizes_formula_injection(client: TestClient) -> None:
    """Regression test for #74: a channel named starting with =, +, -, or @
    would otherwise trigger formula execution when the exported CSV is
    opened in Excel/Google Sheets."""
    _create_channel(client, "=1+1", "#8a8a8a")
    _create_channel(client, "+1234", "#111111")
    _create_channel(client, "-1234", "#222222")
    _create_channel(client, "@SUM(A1:A1)", "#333333")

    response = client.get("/export/channels.csv")

    assert response.status_code == 200
    assert "'=1+1" in response.text
    assert "'+1234" in response.text
    assert "'-1234" in response.text
    assert "'@SUM(A1:A1)" in response.text
    # The raw, unprefixed forms must not appear anywhere in the output.
    assert "\n=1+1" not in response.text
    assert ",=1+1" not in response.text
