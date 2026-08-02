import pytest

from app import manage_users


def test_validate_password_rejects_short_password() -> None:
    with pytest.raises(SystemExit):
        manage_users._validate_password("short-pw")


def test_validate_password_accepts_long_enough_password() -> None:
    manage_users._validate_password("this-is-plenty-long")


def test_create_rejects_short_password_before_touching_db(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = iter(["short-pw", "short-pw"])
    monkeypatch.setattr(manage_users.getpass, "getpass", lambda prompt="": next(inputs))

    with pytest.raises(SystemExit):
        manage_users.create("new-user@example.com")

    assert "at least 12 characters" in capsys.readouterr().err


def test_set_password_rejects_short_password_before_touching_db(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = iter(["short-pw", "short-pw"])
    monkeypatch.setattr(manage_users.getpass, "getpass", lambda prompt="": next(inputs))

    with pytest.raises(SystemExit):
        manage_users.set_password("someone@example.com")

    assert "at least 12 characters" in capsys.readouterr().err


def test_create_key_rejects_zero_max_uses_before_touching_db(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        manage_users.create_key(max_uses=0, expires_days=None)

    assert "at least 1" in capsys.readouterr().err
