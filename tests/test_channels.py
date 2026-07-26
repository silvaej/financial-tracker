import re

from fastapi.testclient import TestClient


def _create_channel(client: TestClient, name: str, color: str = "#8a8a8a") -> str:
    create = client.post("/channels", data={"name": name, "color": color})
    match = re.search(rf'value="{re.escape(name)}">.*?/channels/(\d+)"', create.text, re.DOTALL)
    assert match is not None
    return match.group(1)


def test_create_channel_appears_on_page(client: TestClient) -> None:
    response = client.post("/channels", data={"name": "BPI", "color": "#B8122B"})
    assert response.status_code == 200
    assert "BPI" in response.text


def test_update_channel_renames_it(client: TestClient) -> None:
    create = client.post("/channels", data={"name": "Maya", "color": "#0FA968"})
    assert "Maya" in create.text

    import re

    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    response = client.patch(
        f"/channels/{channel_id}", data={"name": "Maya Savings", "color": "#0FA968"}
    )
    assert response.status_code == 200
    assert "Maya Savings" in response.text


def test_delete_channel(client: TestClient) -> None:
    create = client.post("/channels", data={"name": "Temp Channel", "color": "#8a8a8a"})
    import re

    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    response = client.delete(f"/channels/{channel_id}")
    assert response.status_code == 200
    assert "Temp Channel" not in response.text


def test_delete_channel_in_use_by_payout_period_is_rejected(client: TestClient) -> None:
    import re

    create = client.post("/channels", data={"name": "BDO", "color": "#8a8a8a"})
    match = re.search(r'/channels/(\d+)"', create.text)
    assert match is not None
    channel_id = match.group(1)

    client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "1000", "receiving_channel_id": channel_id},
    )

    response = client.delete(f"/channels/{channel_id}")
    assert response.status_code == 409
    assert "still used" in response.json()["detail"]


def _create_payout_period(client: TestClient, channel_id: str) -> str:
    response = client.post(
        "/payout-periods",
        data={"label": "15th", "income_amount": "0", "receiving_channel_id": channel_id},
    )
    match = re.search(r"/payout-periods/(\d+)", response.text)
    assert match is not None
    return match.group(1)


def test_channel_starts_unplaced_and_can_be_placed_then_repositioned(
    client: TestClient,
) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, channel_id)

    # Not placed yet -> no canvas node, just a toolbox entry.
    before = client.get("/cashflow")
    assert f'data-position-url="/channels/{channel_id}/placement"' not in before.text
    assert "BPI" in before.text

    place = client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "10", "y": "20"},
    )
    assert place.status_code == 200
    assert 'data-x="10.0"' in place.text
    assert 'data-y="20.0"' in place.text

    reposition = client.patch(
        f"/channels/{channel_id}/placement",
        json={"payout_period_id": int(period_id), "x": 123.5, "y": 45.0},
    )
    assert reposition.status_code == 204

    page = client.get("/cashflow")
    assert 'data-x="123.5"' in page.text
    assert 'data-y="45.0"' in page.text


def test_channel_presets_render_on_expenses_page(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert "GCash" in response.text
    assert "BDO" in response.text
    assert "applyChannelPreset(" in response.text


def _png_bytes() -> bytes:
    # Smallest valid 1x1 transparent PNG.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000002000100ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )


def test_upload_channel_logo_is_served_and_replaces_badge_initials(client: TestClient) -> None:
    channel_id = _create_channel(client, "Custom Wallet")

    upload = client.patch(
        f"/channels/{channel_id}",
        data={"name": "Custom Wallet", "color": "#8a8a8a"},
        files={"logo": ("logo.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 200
    assert f'src="/channels/{channel_id}/logo"' in upload.text

    logo = client.get(f"/channels/{channel_id}/logo")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert logo.content == _png_bytes()


def test_upload_channel_logo_rejects_non_image_files(client: TestClient) -> None:
    channel_id = _create_channel(client, "Custom Wallet")

    upload = client.patch(
        f"/channels/{channel_id}",
        data={"name": "Custom Wallet", "color": "#8a8a8a"},
        files={"logo": ("evil.txt", b"not an image", "text/plain")},
    )
    assert upload.status_code == 400


def test_remove_channel_logo_falls_back_to_initials(client: TestClient) -> None:
    channel_id = _create_channel(client, "Custom Wallet")
    client.patch(
        f"/channels/{channel_id}",
        data={"name": "Custom Wallet", "color": "#8a8a8a"},
        files={"logo": ("logo.png", _png_bytes(), "image/png")},
    )

    removed = client.delete(f"/channels/{channel_id}/logo")
    assert removed.status_code == 200
    assert f'src="/channels/{channel_id}/logo"' not in removed.text

    logo = client.get(f"/channels/{channel_id}/logo")
    assert logo.status_code == 404


def test_remove_channel_placement_returns_it_to_the_toolbox(client: TestClient) -> None:
    channel_id = _create_channel(client, "BPI")
    period_id = _create_payout_period(client, channel_id)
    client.post(
        f"/channels/{channel_id}/placement",
        data={"payout_period_id": period_id, "x": "10", "y": "20"},
    )

    removed = client.delete(f"/channels/{channel_id}/placement?payout_period_id={period_id}")
    assert removed.status_code == 200
    assert f'data-position-url="/channels/{channel_id}/placement"' not in removed.text
    assert "BPI" in removed.text
