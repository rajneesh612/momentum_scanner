"""Shared Pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers all models on Base.metadata
from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Iterator[None]:
    """Reset any per-test dependency overrides (e.g. fake providers)."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """An isolated in-memory SQLite session, schema created from Base.metadata."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def db_client(db_session: Session) -> Iterator[TestClient]:
    """A TestClient whose `get_db` dependency is wired to `db_session`."""

    def _get_db_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
