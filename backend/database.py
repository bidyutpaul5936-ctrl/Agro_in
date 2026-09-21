"""
database.py – SQLAlchemy engine + session factory for SQLite.

The database file lands at  backend/agro_in.db  by default.
Override with the environment variable  DATABASE_URL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},   # required for SQLite
    echo=settings.SQL_ECHO,                       # set True to see all SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ── Dependency used inside FastAPI route handlers ──────────────────────────

def get_db():
    """Yield a database session and guarantee it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
