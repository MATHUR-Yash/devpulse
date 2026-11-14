from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from backend import main
from backend.database import create_database_engine
from backend.main import create_app


def test_health_reports_a_working_database(tmp_path):
    app = create_app(tmp_path / "nested" / "test.sqlite3")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_503_if_the_database_query_fails(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    engine = create_database_engine(path)
    monkeypatch.setattr(main, "create_database_engine", lambda _path: engine)

    @event.listens_for(engine, "before_cursor_execute")
    def fail_query(_conn, _cursor, statement, params, _context, _many):
        if statement == "SELECT 1":
            raise OperationalError(statement, params, RuntimeError("test failure"))

    with TestClient(create_app(path)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
