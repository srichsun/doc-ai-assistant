"""Shared test fixtures."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db
from app.models import Base


@pytest.fixture
def sqlite_db(monkeypatch):
    """Point the app's database at a fresh in-memory SQLite for one test.

    One shared connection (StaticPool) so the created tables stick around.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(
        db, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False)
    )
    return engine
