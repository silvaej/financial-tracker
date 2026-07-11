from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import create_channel
from app.seed import seed_if_empty
from tests.conftest import TestingSessionLocal


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _counts(db: Session) -> dict[str, int]:
    return {
        model.__name__: db.query(model).count()
        for model in (
            models.Channel,
            models.PayoutPeriod,
            models.Expense,
            models.Transfer,
            models.Goal,
            models.CreditLine,
            models.Asset,
        )
    }


def test_seed_populates_all_tables_when_empty(db: Session) -> None:
    seed_if_empty(db)

    counts = _counts(db)
    assert all(count > 0 for count in counts.values()), counts


def test_seed_is_a_no_op_on_second_call(db: Session) -> None:
    seed_if_empty(db)
    first_counts = _counts(db)

    seed_if_empty(db)
    second_counts = _counts(db)

    assert first_counts == second_counts


def test_seed_leaves_existing_channels_alone(db: Session) -> None:
    create_channel(db, schemas.ChannelCreate(name="My Own Bank"))

    seed_if_empty(db)

    channel_names = {c.name for c in db.query(models.Channel).all()}
    assert channel_names == {"My Own Bank"}
    assert db.query(models.PayoutPeriod).count() == 0
