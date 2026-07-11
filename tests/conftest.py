import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import get_current_user
from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_USER_ID = 1


def _override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _override_get_current_user() -> models.User:
    db = TestingSessionLocal()
    try:
        user = db.get(models.User, TEST_USER_ID)
        assert user is not None
        return user
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
app.dependency_overrides[get_current_user] = _override_get_current_user


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    db.add(models.User(id=TEST_USER_ID, email="test@example.com", hashed_password="x"))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
