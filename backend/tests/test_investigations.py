import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import api
from backend.tests.test_dashboard import RUN, register


@pytest.fixture
def database(tmp_path, monkeypatch):
    def github(path, **_params):
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [
                RUN, {**RUN, "run_attempt": 2, "conclusion": "success"},
                {**RUN, "id": 23, "status": "in_progress", "conclusion": None},
            ]}
        name = path.rsplit("/", 1)[-1]
        return {"id": 10 if name == "demo" else 11, "private": name == "private",
                "owner": {"login": "example"}, "name": name}

    monkeypatch.setattr(api, "github_get", github)
    monkeypatch.setattr(api, "collect_deployments", lambda *_args, **_kwargs: [])
    return tmp_path / "investigations.sqlite3"


def connect(client, name="demo"):
    reply = client.post("/api/repositories", json={"repository": f"example/{name}"})
    reply.raise_for_status()
    return f"/api/repositories/{reply.json()['id']}"


def investigation_path(base, run):
    return f"{base}/runs/{run['id']}/investigation"


def test_investigation_survives_sync_retry_and_restart(database):
    with TestClient(create_app(database)) as client:
        register(client, "alice").raise_for_status()
        base = connect(client)
        client.post(f"{base}/sync").raise_for_status()
        runs = client.get(f"{base}/dashboard").json()["runs"]
        failed = next(run for run in runs if run["conclusion"] == "failure")
        assert failed["investigation_status"] == "open"
        assert all(run["investigation_status"] is None for run in runs if run != failed)
        path = investigation_path(base, failed)
        assert client.get(path).json() == {
            "status": "open", "cause": "", "notes": "", "updated_at": None, "resolved_at": None,
        }
        tracking = client.post(path, json={"status": "investigating", "cause": " dependency "}).json()
        assert tracking["status"] == "investigating"
        assert tracking["cause"] == "dependency"
        assert tracking["resolved_at"] is None
        payload = {"status": "resolved", "cause": "dependency", "notes": "Pinned the version."}
        first = client.post(path, json=payload).json()
        assert first["resolved_at"] == first["updated_at"]
        again = client.post(path, json=payload).json()
        assert again["resolved_at"] == first["resolved_at"]
        client.post(f"{base}/sync").raise_for_status()
        runs = client.get(f"{base}/dashboard").json()["runs"]
        assert next(run for run in runs if run["id"] == failed["id"])["investigation_status"] == "resolved"

    with TestClient(create_app(database)) as client:
        client.post("/api/auth/login", json={
            "username": "alice", "password": "test-only-password",
        }).raise_for_status()
        assert client.get(path).json() == again
        reopened = client.post(path, json={**payload, "status": "open"}).json()
        assert reopened["status"] == "open"
        assert reopened["resolved_at"] is None
        assert reopened["notes"] == payload["notes"]


def test_only_owners_can_track_completed_failures(database):
    with TestClient(create_app(database)) as client:
        register(client, "alice").raise_for_status()
        base = connect(client)
        client.post(f"{base}/sync").raise_for_status()
        runs = client.get(f"{base}/dashboard").json()["runs"]
        payload = {"status": "investigating", "notes": "Checking the logs."}
        for run in runs:
            if run["conclusion"] == "failure":
                failed = run
            else:
                path = investigation_path(base, run)
                assert client.get(path).status_code == 422
                assert client.post(path, json=payload).status_code == 422
        other_base = connect(client, "other")
        assert client.post(investigation_path(other_base, failed), json=payload).status_code == 404
        path = investigation_path(base, failed)
        for invalid in [
            {"status": "unknown"}, {"status": "resolved", "notes": "  "},
            {**payload, "cause": "x" * 501}, {**payload, "notes": "x" * 2001},
            {**payload, "notes": "contains\x00nul"},
        ]:
            assert client.post(path, json=invalid).status_code == 422
        assert client.post(path, json=payload, headers={"Origin": "https://unrelated.example"}).status_code == 403
        client.post(path, json=payload).raise_for_status()
        client.post("/api/auth/logout").raise_for_status()
        assert client.get(path).status_code == 401
        assert client.post(path, json=payload).status_code == 401
        register(client, "bob").raise_for_status()
        assert client.get(path).status_code == 404
        assert client.post(path, json=payload).status_code == 404
