from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from tests.conftest import TEST_USER_ID, TestingSessionLocal


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def as_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_emails", "test@example.com")


def test_non_admin_gets_404(client: TestClient) -> None:
    response = client.get("/admin")
    assert response.status_code == 404


def test_admin_can_view_dashboard(client: TestClient, as_admin: None) -> None:
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Admin" in response.text
    assert "test@example.com" in response.text


def test_admin_dashboard_shows_orphan_counts(
    client: TestClient, as_admin: None, db: Session
) -> None:
    crud.create_channel(db, schemas.ChannelCreate(name="Orphan Wallet"), user_id=None)

    response = client.get("/admin")
    assert response.status_code == 200
    assert "channels" in response.text


def test_delete_user_removes_their_data(client: TestClient, as_admin: None, db: Session) -> None:
    other = crud.create_user(db, "other@example.com")
    channel = crud.create_channel(
        db, schemas.ChannelCreate(name="Other's Wallet"), user_id=other.id
    )
    db.commit()
    other_id = other.id
    channel_id = channel.id

    response = client.post(f"/admin/users/{other_id}/delete")
    assert response.status_code == 200
    # The delete happened on a different Session (the request's), so this
    # session's identity map still holds pre-delete instances -- force it to
    # re-query rather than serve stale cached objects.
    db.expire_all()
    assert crud.get_user_by_email(db, "other@example.com") is None
    assert db.get(type(channel), channel_id) is None


def test_admin_cannot_delete_own_account(client: TestClient, as_admin: None) -> None:
    response = client.post(f"/admin/users/{TEST_USER_ID}/delete")
    assert response.status_code == 400


def test_delete_nonexistent_user_404s(client: TestClient, as_admin: None) -> None:
    response = client.post("/admin/users/999999/delete")
    assert response.status_code == 404


def test_create_and_revoke_signup_key(client: TestClient, as_admin: None, db: Session) -> None:
    response = client.post("/admin/signup-keys", data={"max_uses": "3", "expires_days": ""})
    assert response.status_code == 200
    keys = crud.list_signup_keys(db)
    assert len(keys) == 1
    assert keys[0].max_uses == 3

    revoke_response = client.post(f"/admin/signup-keys/{keys[0].id}/revoke")
    assert revoke_response.status_code == 200
    assert crud.list_signup_keys(db) == []


def test_revoke_nonexistent_key_404s(client: TestClient, as_admin: None) -> None:
    response = client.post("/admin/signup-keys/999999/revoke")
    assert response.status_code == 404


def test_assign_orphans_moves_rows_to_target_user(
    client: TestClient, as_admin: None, db: Session
) -> None:
    crud.create_channel(db, schemas.ChannelCreate(name="Orphan Wallet"), user_id=None)
    db.commit()

    response = client.post(
        "/admin/orphans/channels/assign", data={"target_user_id": str(TEST_USER_ID)}
    )
    assert response.status_code == 200
    channels = crud.list_channels(db, TEST_USER_ID)
    assert any(c.name == "Orphan Wallet" for c in channels)


def test_assign_orphans_unknown_table_404s(client: TestClient, as_admin: None) -> None:
    response = client.post(
        "/admin/orphans/not_a_real_table/assign", data={"target_user_id": str(TEST_USER_ID)}
    )
    assert response.status_code == 404


def test_assign_orphans_unknown_user_404s(client: TestClient, as_admin: None) -> None:
    response = client.post("/admin/orphans/channels/assign", data={"target_user_id": "999999"})
    assert response.status_code == 404
