import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import api


def test_postgres_keeps_workflow_and_deployment_history_across_restarts(monkeypatch):
    database_url = os.getenv("DEVPULSE_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set DEVPULSE_TEST_POSTGRES_URL to a disposable PostgreSQL database.")
    monkeypatch.setenv("DEVPULSE_DATABASE_URL", database_url)
    username = "test-" + uuid4().hex
    repo_url = "/repos/example/demo"
    sync_time = "2026-11-19T12:00:00Z"
    responses = {
        repo_url: {"id": 123, "private": False, "owner": {"login": "example"}, "name": "demo"},
        repo_url + "/actions/runs": {"workflow_runs": [{
            "id": 12345678901,
            "head_sha": "a" * 40,
            "status": "completed",
            "conclusion": "success",
            "run_started_at": sync_time,
            "updated_at": sync_time,
        }]},
    }
    monkeypatch.setattr(api, "github_get", lambda path, **_params: responses[path])
    monkeypatch.setattr(api, "collect_deployments", lambda _base: [
        api.deployment_values(
            {"id": 19, "environment": "production", "sha": "a" * 40, "created_at": sync_time},
            {"state": "success"},
        )
    ])
    credentials = {"username": username, "password": "test-only-password"}
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/register", json={
            **credentials, "email": username + "@example.com",
        }).status_code == 201
        repo = client.post("/api/repositories", json={"repository": "example/demo"}).json()
        assert client.post("/api/repositories", json={"repository": "example/demo"}).json() == repo
        base = f"/api/repositories/{repo['id']}"
        for _ in range(2):
            assert client.post(f"{base}/sync").json() == {"runs": 1, "deployments": 1}

    with TestClient(create_app()) as restarted:
        assert restarted.get("/health").status_code == 200
        assert restarted.post("/api/auth/login", json=credentials).status_code == 200
        dashboard = restarted.get(f"{base}/dashboard").json()
        assert [run["conclusion"] for run in dashboard["runs"]] == ["success"]
        assert [item["status"] for item in dashboard["deployments"]] == ["success"]
        assert dashboard["last_sync"]["status"] == "success"
