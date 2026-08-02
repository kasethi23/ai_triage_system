"""Test setup: isolate the DB + audio storage to a temp dir and set a known
bearer token BEFORE any app module is imported (config/engine are import-time)."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="clinroute-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["AUDIO_STORAGE_DIR"] = f"{_TMP}/audio"
os.environ["API_BEARER_TOKEN"] = "test-token"
os.environ.pop("RAILWAY_ENVIRONMENT", None)  # never look like prod

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

TEST_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def fresh_db():
    """Recreate all tables before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
