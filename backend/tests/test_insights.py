from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime
from backend.models import GitHubDeployment

from backend.main import create_app
from backend.routers import api
from backend.services import insights
from backend.tests.test_dashboard import register, RUN


def test_insight_routes_isolate_accounts_compare_baseline_and_cache_reports(tmp_path, monkeypatch):
    rows = [
        {**RUN, "id": 21, "head_sha": "b" * 40, "conclusion": "success"},
        {**RUN, "id": 22},
        {**RUN, "id": 23, "head_branch": "other", "conclusion": "success"},
    ]
    def github(path, **params):
        if path.endswith("/actions/runs"):
            return {"workflow_runs": rows}
        if "/jobs" in path:
            return {"jobs": [{"name": "Tests", "conclusion": "failure", "steps": [{"name": "pytest", "conclusion": "failure"}]}]}
        if "/commits/" in path:
            return {"sha": "a" * 40}
        return {"id": 10, "private": False, "owner": {"login": "example"},
                "name": "demo", "default_branch": "main"}
    monkeypatch.setattr(api, "github_get", github)
    monkeypatch.setattr(api, "collect_deployments", lambda *args, **kwargs: [])
    calls = []
    def report(base, run_id, attempt, token):
        calls.append(run_id)
        return {"available": True, "cases": [{"class": "suite", "name": "case",
                "status": "passed" if run_id == 21 else "failure"}]}
    monkeypatch.setattr(api, "read_cases", report)
    with TestClient(create_app(tmp_path / "insights.db")) as client:
        register(client, "alice")
        repo = client.post("/api/repositories", json={"repository": "example/demo"}).json()
        base = f"/api/repositories/{repo['id']}"
        client.post(base + "/sync").raise_for_status()
        runs = client.get(base + "/dashboard").json()["runs"]
        selected = next(r for r in runs if r["conclusion"] == "failure")
        path = base + "/runs/" + str(selected["id"])
        comparison = client.get(path + "/comparison").json()
        assert comparison["baseline"]["sha"] == "b" * 40
        assert comparison["failed_steps"] == [{"job": "Tests", "step": "pytest"}]
        history = client.get(path + "/test-history").json()
        assert history["reports_available"] == 2
        assert history["candidates"][0]["same_commit"] is False
        assert client.get(path + "/test-history").status_code == 200
        assert len(calls) == 2
        ready = client.get(base + "/readiness").json()
        assert not ready["ready"]
        assert not ready["checks"][0]["passed"]
        with Session(client.app.state.engine) as db:
            for github_id, state, minute, sha in [(1, "inactive", 2, "b" * 40), (2, "success", 1, "a" * 40)]:
                db.add(GitHubDeployment(repository_id=repo["id"], github_id=github_id,
                    environment="production", version=sha, commit_sha=sha, status=state,
                    updated_at=datetime(2026, 11, 19, 10, minute)))
            db.commit()
        assert client.get(base + "/readiness").json()["checks"][2]["passed"]
        portfolio = client.get("/api/portfolio").json()["repositories"]
        assert portfolio[0]["failed"] == 1
        client.post("/api/auth/logout")
        register(client, "bob")
        assert client.get("/api/portfolio").json()["repositories"] == []
        for endpoint in [path + "/comparison", path + "/test-history", base + "/readiness"]:
            assert client.get(endpoint).status_code == 404


def test_flaky_signals_ignore_duplicate_names_and_skipped_results():
    def case(status): return {"class": "suite", "name": "case", "status": status}
    def run(i): return SimpleNamespace(id=i, commit_sha="a", run_attempt=i)
    result = insights.test_signals([(run(1), [case("failure")]), (run(2), [case("passed")])])
    assert result[0]["same_commit"]
    assert not insights.test_signals([(run(1), [case("failure"), case("failure")]), (run(2), [case("passed")])])
    assert not insights.test_signals([(run(1), [case("skipped")]), (run(2), [case("passed")])])


def test_readiness_requires_current_sha_passed_tests_and_latest_production():
    run = SimpleNamespace(github_run_id=1, commit_sha="head", status="completed", conclusion="success")
    good = SimpleNamespace(environment="production", status="success", commit_sha="head")
    bad = SimpleNamespace(environment="production", status="failure", commit_sha="head")
    assert insights.readiness([run], [[{"status": "passed"}]], [good], "head")["ready"]
    for reports, deployments, head in [([], [good], "head"), ([[{"status": "skipped"}]], [good], "head"),
                                       ([[{"status": "passed"}]], [bad, good], "head"),
                                       ([[{"status": "passed"}]], [good], "new-head")]:
        assert not insights.readiness([run], reports, deployments, head)["ready"]
