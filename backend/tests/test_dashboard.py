import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import api


RUN = {
    "id": 22, "run_attempt": 1, "name": "CI", "status": "completed",
    "conclusion": "failure", "head_branch": "main", "head_sha": "a" * 40,
    "run_started_at": "2026-11-13T10:00:00Z", "updated_at": "2026-11-13T10:02:00Z",
}


def register(client, username):
    return client.post("/api/auth/register", json={
        "username": username, "email": username + "@example.com", "password": "test-only-password",
    })


def test_account_repository_sync_and_workflow_timeline(tmp_path, monkeypatch):
    def github(path, **params):
        return {
            "/repos/example/demo": {
                "id": 10, "private": False, "owner": {"login": "example"}, "name": "demo",
            },
            "/repos/example/demo/actions/runs": {"workflow_runs": [RUN]},
            "/repos/example/demo/actions/runs/22/attempts/1/jobs": {"jobs": [{
                "name": "Test", "status": "completed", "conclusion": "failure",
                "steps": [{"name": "Run pytest", "conclusion": "failure"}],
            }]},
        }[path]

    monkeypatch.setattr(api, "github_get", github)
    monkeypatch.setattr(api, "collect_deployments", lambda _, token=None: [])
    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        assert "Pipeline overview" in client.get("/").text
        assert client.get("/api/repositories").status_code == 401
        assert register(client, "alice").status_code == 201
        repo = client.post("/api/repositories", json={"repository": "example/demo"})
        assert repo.status_code == 201
        base = f"/api/repositories/{repo.json()['id']}"
        assert client.post(f"{base}/sync").json()["runs"] == 1
        assert client.post(f"{base}/sync").status_code == 200
        runs = client.get(f"{base}/dashboard").json()["runs"]
        assert len(runs) == 1
        details = client.get(f"{base}/runs/{runs[0]['id']}").json()
        assert details["jobs"][0]["steps"][0]["conclusion"] == "failure"

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert register(client, "bob").status_code == 201
        assert client.get(f"{base}/dashboard").status_code == 404
        assert client.post("/api/auth/login", json={
            "username": "alice", "password": "test-only-password",
        }).status_code == 200
        assert client.get(f"{base}/dashboard").status_code == 200


def test_webhook_requires_a_valid_signature_and_updates_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVPULSE_WEBHOOK_SECRET", "local-test-secret")
    monkeypatch.setattr(api, "github_get", lambda *_args, **_kwargs: {
        "id": 10, "private": False, "owner": {"login": "example"}, "name": "demo",
    })
    body = json.dumps({"repository": {"id": 10, "private": False}, "workflow_run": RUN}).encode()
    signature = hmac.new(b"local-test-secret", body, hashlib.sha256).hexdigest()
    route = "/api/webhooks/github"
    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        assert register(client, "alice").status_code == 201
        repo = client.post("/api/repositories", json={"repository": "example/demo"}).json()
        assert client.post(route, content=body).status_code == 403
        assert client.post(route, content=body, headers={
            "X-Hub-Signature-256": "sha256=" + signature, "X-GitHub-Event": "workflow_run",
        }).status_code == 204
        assert client.get(f"/api/repositories/{repo['id']}/dashboard").json()["runs"][0]["conclusion"] == "failure"


def test_deployment_webhooks_keep_the_latest_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVPULSE_WEBHOOK_SECRET", "local-test-secret")
    monkeypatch.setattr(api, "github_get", lambda *_args, **_kwargs: {
        "id": 10, "private": False, "owner": {"login": "example"}, "name": "demo",
    })
    payload = {
        "repository": {"id": 10, "private": False},
        "deployment": {
            "id": 7, "environment": "production", "sha": "a" * 40, "ref": "v1",
        },
    }
    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        assert register(client, "alice").status_code == 201
        repo = client.post("/api/repositories", json={"repository": "example/demo"}).json()
        for state, minute in [("success", "02"), ("in_progress", "01"), ("success", "02")]:
            payload["deployment_status"] = {
                "state": state, "created_at": f"2026-11-13T10:{minute}:00Z",
            }
            body = json.dumps(payload).encode()
            signature = hmac.new(b"local-test-secret", body, hashlib.sha256).hexdigest()
            response = client.post("/api/webhooks/github", content=body, headers={
                "X-Hub-Signature-256": "sha256=" + signature,
                "X-GitHub-Event": "deployment_status",
            })
            assert response.status_code == 204
        deployments = client.get(f"/api/repositories/{repo['id']}/dashboard").json()["deployments"]
        assert [(item["id"], item["status"]) for item in deployments] == [(7, "success")]
