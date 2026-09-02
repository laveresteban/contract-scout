import os
from pathlib import Path

# Use a file-based test database so all sessions share the same data.
TEST_DB_PATH = Path(__file__).parent / "test.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["CORS_ORIGINS"] = "http://localhost"

# Remove any stale database file before importing the app.
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

import pytest
from fastapi.testclient import TestClient

from app.database import get_db, init_db
from app.main import app
from app.models import JobORM, SessionLocal, engine


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    init_db()
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    db = SessionLocal()
    try:
        db.query(JobORM).delete(synchronize_session=False)
        db.commit()
        yield db
    finally:
        db.query(JobORM).delete(synchronize_session=False)
        db.commit()
        db.close()
