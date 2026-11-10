"""Centralized PostgreSQL connection management."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def get_database_url() -> str:
    """Return DATABASE_URL or fail with an actionable message."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Copy .env.example to .env "
            "and set the PostgreSQL connection string."
        )
    return url


def get_engine(*, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine with connection health checks."""
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 10},
        echo=echo,
    )


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Provide a transaction boundary that commits or rolls back atomically."""
    db_engine = engine or get_engine()
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_healthcheck(engine: Engine | None = None) -> bool:
    """Execute a minimal query to prove PostgreSQL is reachable."""
    db_engine = engine or get_engine()
    with db_engine.connect() as connection:
        return bool(connection.execute(text("SELECT 1")).scalar_one() == 1)
