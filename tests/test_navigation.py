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


def test_form_fields_have_accessible_names(client: TestClient) -> None:
    """Regression test for #78: every form field's 'label' was a styled
    <span> positioned near the input with no programmatic association at
    all (grep -rn '<label for=' app/templates returned zero matches).
    Account page fields now use real <label for>; table/add-row fields
    (which already show their label via the column <th>/data-label) use
    aria-label instead, since a second visible label there would be
    redundant -- spot-check a representative field on each affected page."""
    account = client.get("/account").text
    assert 'for="display_name"' in account
    assert 'for="currency_code"' in account
    assert 'for="timezone"' in account

    expenses = client.get("/expenses").text
    assert 'aria-label="Channel name"' in expenses
    assert 'aria-label="Payout day"' in expenses
    assert 'aria-label="Expense name"' in expenses

    assert 'aria-label="Asset name"' in client.get("/assets").text
    assert 'aria-label="Credit line name"' in client.get("/credit").text
    assert 'aria-label="Goal name"' in client.get("/goals").text


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


def test_unmatched_route_renders_custom_404_page(client: TestClient) -> None:
    """Regression test for #169: a plain navigation to an unmatched route
    (single- or multi-segment) gets the app's own styled not-found page
    with a real 404 status, not FastAPI's raw unstyled JSON error."""
    response = client.get("/nonsense")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "Page not found" in response.text
    assert 'id="rail"' in response.text

    multi_segment = client.get("/nonsense/deeply/nested")
    assert multi_segment.status_code == 404
    assert "Page not found" in multi_segment.text


def test_boosted_unmatched_route_returns_fragment_with_200(client: TestClient) -> None:
    """Regression test for #169: htmx doesn't swap non-2xx responses, so a
    boosted nav click to an unmatched route must get a 200 fragment (no
    <html>/<nav>) for #page-content to actually receive it, instead of
    falling through to the generic error-toast path."""
    response = client.get("/nonsense", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Page not found" in response.text
    assert "<html" not in response.text
    assert "<nav" not in response.text


def test_app_raised_404_is_not_swallowed_by_the_not_found_page(client: TestClient) -> None:
    """Regression test for #169: the custom 404 page must only kick in for
    genuinely unmatched routes -- an HTTPException(404) raised by a matched
    route's own handler (ownership checks, missing avatar/logo, admin
    gating, ...) needs to keep returning its specific JSON `detail` so
    base.html's global htmx:responseError toast still shows a meaningful
    message instead of a generic 'page not found' fragment."""
    response = client.patch("/expenses/999999/paid", data={"paid": "on"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "Page not found" not in response.text


def test_mobile_gate_markup_present_on_plain_page_load(client: TestClient) -> None:
    """Regression test for #168: the desktop-only notice is always in the
    DOM (a pure-CSS gate, shown/hidden by a media query, not JS), so a
    plain full-page load must always render it alongside the normal shell
    -- there is no server-side viewport detection to assert on instead."""
    text = client.get("/").text
    assert 'id="mobile-gate"' in text
    assert "Desktop only for now" in text
    assert 'id="rail"' in text


def test_favicon_served_and_linked_on_every_page(client: TestClient) -> None:
    """Regression test for #132: there was previously no favicon/apple-touch-
    icon <link> anywhere, on either the authenticated app shell or the
    standalone login/signup pages."""
    favicon = client.get("/static/favicon.svg")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")

    for path in ("/", "/login", "/signup"):
        text = client.get(path).text
        assert 'rel="icon"' in text
        assert "static/favicon.svg" in text
        assert 'rel="apple-touch-icon"' in text
