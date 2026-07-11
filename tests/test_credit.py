import re

from fastapi.testclient import TestClient

from app import crud, models


def _create_channel(client: TestClient, name: str = "BPI", color: str = "#0FA968") -> str:
    create = client.post("/channels", data={"name": name, "color": color})
    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    return match.group(1)


def test_create_credit_line_appears_on_page(client: TestClient) -> None:
    response = client.post("/credit", data={"name": "Maya Black", "limit": "111000", "used": "0"})
    assert response.status_code == 200
    assert "Maya Black" in response.text


def test_update_credit_line_renames_and_changes_amounts(client: TestClient) -> None:
    create = client.post("/credit", data={"name": "Old Card", "limit": "1000", "used": "0"})
    match = re.search(r'/credit/(\d+)"', create.text)
    assert match is not None
    credit_id = match.group(1)

    response = client.patch(
        f"/credit/{credit_id}", data={"name": "New Card", "limit": "2000", "used": "500"}
    )
    assert response.status_code == 200
    assert "New Card" in response.text
    assert "Old Card" not in response.text


def test_delete_credit_line(client: TestClient) -> None:
    create = client.post("/credit", data={"name": "Temp Card", "limit": "1000", "used": "0"})
    match = re.search(r'/credit/(\d+)"', create.text)
    assert match is not None
    credit_id = match.group(1)

    response = client.delete(f"/credit/{credit_id}")
    assert response.status_code == 200
    assert "Temp Card" not in response.text


def test_credit_empty_state(client: TestClient) -> None:
    response = client.get("/credit")
    assert response.status_code == 200
    assert "No credit lines yet" in response.text


def test_create_credit_line_with_channel(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    response = client.post(
        "/credit",
        data={
            "name": "BPI Blue Mastercard",
            "limit": "196000",
            "used": "0",
            "channel_id": channel_id,
        },
    )
    assert response.status_code == 200
    assert "BPI Blue Mastercard" in response.text
    assert "BPI" in response.text


def test_create_credit_line_without_channel(client: TestClient) -> None:
    response = client.post(
        "/credit",
        data={"name": "No Channel Card", "limit": "1000", "used": "0", "channel_id": ""},
    )
    assert response.status_code == 200
    assert "No Channel Card" in response.text


def test_credit_utilization_level_ok_below_80_percent() -> None:
    line = models.CreditLine(name="Card", limit=1000, used=790)
    result = crud.credit_utilization(line)
    assert result["level"] == "ok"


def test_credit_utilization_level_amber_at_80_percent() -> None:
    line = models.CreditLine(name="Card", limit=1000, used=800)
    result = crud.credit_utilization(line)
    assert result["level"] == "amber"


def test_credit_utilization_level_red_at_100_percent() -> None:
    line = models.CreditLine(name="Card", limit=1000, used=1000)
    result = crud.credit_utilization(line)
    assert result["level"] == "red"


def test_credit_warn_pill_shown_for_near_limit_line(client: TestClient) -> None:
    response = client.post(
        "/credit", data={"name": "Near Limit Card", "limit": "1000", "used": "850"}
    )
    assert response.status_code == 200
    assert "warn-amber" in response.text
    assert "Near limit" in response.text


def test_credit_warn_pill_shown_for_over_limit_line(client: TestClient) -> None:
    response = client.post(
        "/credit", data={"name": "Over Limit Card", "limit": "1000", "used": "1200"}
    )
    assert response.status_code == 200
    assert "warn-red" in response.text
    assert "Over limit" in response.text
