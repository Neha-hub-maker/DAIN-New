"""Test configuration using an isolated SQLite database."""

import os
from pathlib import Path

TEST_DATABASE_PATH = Path(__file__).parent / "dain_test.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["INSTITUTIONAL_EMAIL_DOMAIN"] = "du.ac.bd"
os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "true"
os.environ["EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
