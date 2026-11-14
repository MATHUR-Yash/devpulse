"""SQLite configuration shared by the app and the tests."""

import os
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine

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
