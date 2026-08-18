import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.auth import get_current_user
from app.main import app
from tests.conftest import TEST_USER_ID, TestingSessionLocal
from tests.conftest import oauth_login as _oauth_login


@pytest.fixture
def real_client() -> Generator[TestClient, None, None]:
    """A client that goes through the real get_current_user dependency (session
    cookie based), instead of the global test override every other test uses."""
    original = app.dependency_overrides.pop(get_current_user, None)
    yield TestClient(app)
    if original is not None:
        app.dependency_overrides[get_current_user] = original


def _create_user(email: str) -> int:
    db = TestingSessionLocal()
    try:
        user = crud.create_user(db, email)
        return user.id
    finally:
        db.close()


def _login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str = "alice@example.com"
) -> None:
    _oauth_login(client, monkeypatch, email=email, provider_user_id=f"g-{email}")


def _create_channel(client: TestClient, name: str = "GCash") -> str:
    response = client.post("/channels", data={"name": name, "color": "#007dfe"})
    match = re.search(r'hx-delete="/channels/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def _create_payout_period(client: TestClient, channel_id: str, label: str = "15th") -> str:
    response = client.post(
        "/payout-periods",
        data={"label": label, "income_amount": "1000", "receiving_channel_id": channel_id},
    )
    match = re.search(r'hx-delete="/payout-periods/(\d+)"', response.text)
    assert match is not None
    return match.group(1)


def _element_classes(html: str, element_id: str) -> str:
    # djlint wraps long tags across lines, so id="..." and class="..." aren't
    # necessarily on the same line/adjacent with a single space -- match
    # across whitespace instead of relying on exact source formatting.
    match = re.search(rf'id="{element_id}"\s+class="([^"]*)"', html)
    assert match is not None, f"couldn't find #{element_id} with a class attribute"
    return match.group(1)


def test_root_redirects_to_expenses_when_onboarding_needed(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/expenses"


def test_root_htmx_request_gets_hx_redirect_to_expenses(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)

    response = real_client.get("/", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/expenses"


def test_root_still_redirects_after_channel_but_before_payout_period(
    real_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    _create_channel(real_client)

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/expenses"


def test_root_does_not_redirect_once_onboarding_skipped(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    real_client.post("/onboarding/skip")

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert 'id="overview-page"' in response.text


def test_root_does_not_redirect_once_all_three_prerequisites_exist(
    real_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    channel_id = _create_channel(real_client)
    period_id = _create_payout_period(real_client, channel_id)
    real_client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "500",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )

    response = real_client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert 'id="overview-page"' in response.text


def test_expenses_page_shows_step_1_banner_with_open_channel_row(
    real_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)

    response = real_client.get("/expenses")
    assert response.status_code == 200
    assert "Step 1 of 3" in response.text
    assert "flex" in _element_classes(response.text, "add-channel-row")
    assert "hidden" in _element_classes(response.text, "add-channel-trigger")


def test_expenses_page_shows_step_2_banner_after_channel_created(
    real_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    _create_channel(real_client, "GCash")

    response = real_client.get("/expenses")
    assert response.status_code == 200
    assert "Step 2 of 3" in response.text
    assert "lands in GCash" in response.text
    assert "hidden" not in _element_classes(response.text, "add-payout-row")


def test_expenses_page_shows_step_3_banner_after_payout_period_created(
    real_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    channel_id = _create_channel(real_client, "GCash")
    _create_payout_period(real_client, channel_id)

    response = real_client.get("/expenses")
    assert response.status_code == 200
    assert "Step 3 of 3" in response.text
    assert "against GCash" in response.text
    assert "hidden" not in _element_classes(response.text, "add-expense-row")
    assert "Skip" in response.text and "add bills later" in response.text


def test_creating_first_expense_completes_onboarding(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)
    channel_id = _create_channel(real_client, "GCash")
    period_id = _create_payout_period(real_client, channel_id)

    response = real_client.post(
        "/expenses",
        data={
            "name": "Rent",
            "amount": "500",
            "payout_period_id": period_id,
            "channel_id": channel_id,
        },
    )
    assert response.status_code == 200
    assert "onboard-banner" not in response.text

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "alice@example.com")
        assert user is not None
        assert user.onboarding_completed_at is not None
    finally:
        db.close()

    overview = real_client.get("/", follow_redirects=False)
    assert overview.status_code == 200
    assert 'id="overview-page"' in overview.text


def test_skip_onboarding_hides_banner_and_persists(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user("alice@example.com")
    _login(real_client, monkeypatch)

    response = real_client.post("/onboarding/skip")
    assert response.status_code == 200
    assert "onboard-banner" not in response.text

    db = TestingSessionLocal()
    try:
        user = crud.get_user_by_email(db, "alice@example.com")
        assert user is not None
        assert user.onboarding_completed_at is not None
    finally:
        db.close()

    again = real_client.get("/expenses")
    assert "onboard-banner" not in again.text


def test_skip_onboarding_requires_login(real_client: TestClient) -> None:
    response = real_client.post("/onboarding/skip", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# --- Per-section nudge (#138) -------------------------------------------------
# Crud-level coverage for crud.needs_nudge()/dismiss_nudge() -- the four
# section-specific TestClient tests (test_goals.py, test_credit.py,
# test_assets.py, test_cashflow.py) cover the actual pages; these cover the
# underlying logic directly, including cases none of those four need to
# repeat (independence between sections, dismissal surviving data later
# being added).


def test_needs_nudge_stays_dismissed_after_data_is_added_later(client: TestClient) -> None:
    """A dismissal is permanent -- adding data afterwards shouldn't matter,
    since needs_nudge() already returns False once is_empty=False regardless
    of the dismissal row. This pins that "dismissed while empty" doesn't
    somehow get treated differently from "dismissed then later has data"."""
    user_id = TEST_USER_ID
    db = TestingSessionLocal()
    try:
        assert crud.needs_nudge(db, user_id, "goals", is_empty=True) is True
        crud.dismiss_nudge(db, user_id, "goals")
        assert crud.needs_nudge(db, user_id, "goals", is_empty=True) is False
        # Once real data exists, is_empty=False is passed in by the caller
        # (goals_page_data) regardless of the dismissal row -- still False.
        assert crud.needs_nudge(db, user_id, "goals", is_empty=False) is False
    finally:
        db.close()


def test_needs_nudge_sections_are_independent(client: TestClient) -> None:
    user_id = TEST_USER_ID
    db = TestingSessionLocal()
    try:
        crud.dismiss_nudge(db, user_id, "goals")
        assert crud.needs_nudge(db, user_id, "goals", is_empty=True) is False
        assert crud.needs_nudge(db, user_id, "credit", is_empty=True) is True
    finally:
        db.close()


def test_dismiss_nudge_is_idempotent(client: TestClient) -> None:
    """Dismissing an already-dismissed section shouldn't raise (e.g. a
    duplicate double-click/request) or create a second row -- the
    UniqueConstraint on (user_id, section) would reject that."""
    user_id = TEST_USER_ID
    db = TestingSessionLocal()
    try:
        crud.dismiss_nudge(db, user_id, "assets")
        crud.dismiss_nudge(db, user_id, "assets")
        assert crud.needs_nudge(db, user_id, "assets", is_empty=True) is False
    finally:
        db.close()
