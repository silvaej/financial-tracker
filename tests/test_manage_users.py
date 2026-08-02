from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app import crud, manage_users
from tests.conftest import TestingSessionLocal


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _use_test_session(monkeypatch: pytest.MonkeyPatch) -> None:
    # manage_users.py opens its own session against app.database.SessionLocal
    # (the real DATABASE_URL engine) rather than taking a `db` dependency --
    # redirect it to the shared in-memory test DB so these tests can see and
    # assert on what it writes.
    monkeypatch.setattr(manage_users, "SessionLocal", TestingSessionLocal)


def test_create_makes_a_passwordless_account(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    manage_users.create("new-user@example.com")

    user = crud.get_user_by_email(db, "new-user@example.com")
    assert user is not None
    assert "Created user" in capsys.readouterr().out


def test_create_rejects_duplicate_email(capsys: pytest.CaptureFixture[str]) -> None:
    manage_users.create("dup@example.com")

    with pytest.raises(SystemExit):
        manage_users.create("dup@example.com")

    assert "already exists" in capsys.readouterr().err


def test_create_key_rejects_zero_max_uses_before_touching_db(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        manage_users.create_key(max_uses=0, expires_days=None)

    assert "at least 1" in capsys.readouterr().err
