"""SQLAlchemy database engine, session, and declarative base.

This module only establishes the database connection/session architecture.
Business tables (stocks, price_history, momentum_scores, watchlists, users,
market_indices, ...) will be added later as SQLAlchemy models under
app/models/, using `Base` defined here.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
