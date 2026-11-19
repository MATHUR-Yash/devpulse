"""Database configuration shared by the app and the tests."""

import os
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def database_path() -> Path:
    """Read the configured SQLite file path or use the project default."""
    configured_path = os.getenv("DEVPULSE_DB_PATH") or "data/devpulse.sqlite3"
    return (PROJECT_ROOT / Path(configured_path).expanduser()).resolve()


def create_database_engine(path: Path) -> Engine:
    """Build a SQLite engine with foreign keys enabled on every connection."""
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _connection_record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    return engine


def create_postgres_engine(database_url: str) -> Engine:
    """Use the configured PostgreSQL database for durable hosted storage."""
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise ValueError("DEVPULSE_DATABASE_URL must be a valid PostgreSQL URL.") from None
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("DEVPULSE_DATABASE_URL must be a PostgreSQL URL.")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


def insert_for(db: Session, model):
    """Construct an insert that supports ON CONFLICT on either database."""
    insert = postgresql_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    return insert(model)
