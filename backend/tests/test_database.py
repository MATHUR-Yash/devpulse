import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import create_database_engine
from backend.main import create_app
from backend.models import Deployment, Repository, SyncHistory, User, WorkflowRun


def test_startup_creates_all_tables(tmp_path):
    path = tmp_path / "test.sqlite3"
    with TestClient(create_app(path)):
        with closing(sqlite3.connect(path)) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()

    assert {name for (name,) in tables} == {
        "users",
        "repositories",
        "workflow_runs",
        "deployments",
        "sync_history",
        "browser_sessions",
        "github_deployments",
    }


def test_pipeline_history_is_linked_to_a_repository(tmp_path):
    path = tmp_path / "test.sqlite3"
    with TestClient(create_app(path)):
        pass

    engine = create_database_engine(path)
    try:
        with Session(engine) as session:
            repository = Repository(
                github_repo_id=12345,
                owner="example",
                name="demo",
                user=User(
                    username="developer",
                    email="dev@example.com",
                    password_hash="test-hash",
                ),
            )
            repository.workflow_runs.append(
                WorkflowRun(
                    github_run_id=67890,
                    workflow_name="CI",
                    status="completed",
                    conclusion="success",
                    branch="main",
                    commit_sha="a" * 40,
                )
            )
            repository.deployments.append(Deployment(version="0.1.0", status="pending"))
            repository.sync_records.append(SyncHistory(status="success"))
            session.add(repository)
            session.flush()
            repository_id = repository.id
            session.commit()

        with Session(engine) as session:
            saved = session.get(Repository, repository_id)
            assert saved.user.username == "developer"
            assert saved.workflow_runs[0].conclusion == "success"
            assert saved.deployments[0].version == "0.1.0"
            assert saved.sync_records[0].synced_at is not None

            session.add(SyncHistory(repository_id=999, status="success"))
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        engine.dispose()
