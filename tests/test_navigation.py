from fastapi.testclient import TestClient


def test_root_renders_overview(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="overview-page"' in response.text


def test_expenses_has_its_own_route(client: TestClient) -> None:
    response = client.get("/expenses")
    assert response.status_code == 200
    assert 'id="expenses-page"' in response.text


def test_boosted_nav_request_returns_fragment_only(client: TestClient) -> None:
    response = client.get("/goals", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert 'id="goals-page"' in response.text
    assert "<html" not in response.text
    assert "<nav" not in response.text


def test_plain_request_returns_full_page(client: TestClient) -> None:
    response = client.get("/goals")
    assert response.status_code == 200
    assert 'id="goals-page"' in response.text
    assert "<html" in response.text
    assert 'id="rail"' in response.text


def test_boosted_account_request_returns_fragment_only(client: TestClient) -> None:
    response = client.get("/account", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert 'id="account-page"' in response.text
    assert "<html" not in response.text
    assert "<nav" not in response.text


def test_plain_account_request_returns_full_page(client: TestClient) -> None:
    response = client.get("/account")
    assert response.status_code == 200
    assert 'id="account-page"' in response.text
    assert "<html" in response.text
    assert 'id="rail"' in response.text


def test_rail_nav_items_have_accessible_names(client: TestClient) -> None:
    """Regression test for #76: the rail's .tab-label spans are hidden via
    JS while the rail is collapsed, so each nav item/theme-toggle/logout
    button needs its own aria-label to keep an accessible name regardless of
    collapsed state."""
    response = client.get("/")
    text = response.text

    for label in ("Overview", "Expenses", "Cash Flow", "Goals", "Credit", "Assets", "Account"):
        assert f'aria-label="{label}"' in text
    assert 'aria-label="Dark mode"' in text
    assert 'aria-label="Log out"' in text


def test_confirm_and_alert_modals_have_dialog_semantics(client: TestClient) -> None:
    """Regression test for #77: the confirm/alert modals -- used for every
    destructive-delete confirmation and error alert app-wide -- previously
    had no role=dialog/aria-modal at all."""
    text = client.get("/").text

    assert 'id="confirm-modal-message"' in text
    assert 'role="dialog"' in text
    assert 'aria-modal="true"' in text
    assert 'aria-describedby="confirm-modal-message"' in text
    assert 'aria-describedby="alert-modal-message"' in text
