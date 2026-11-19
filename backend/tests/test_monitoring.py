import hashlib
import hmac
import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth import COOKIE, token_hash
from backend.main import create_app
from backend.routers import api
from backend.services import junit, oauth
from backend.tests.test_dashboard import register, RUN


def archive(xml):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as bundle:
        bundle.writestr("junit.xml", xml)
    return buffer.getvalue()


def test_junit_outcomes_and_invalid_xml():
    cases = junit.parse_report(archive('<testsuite><testcase name="a"/><testcase name="b"><failure/>'
                                      '</testcase><testcase><error/></testcase><testcase><skipped/>'
                                      '</testcase></testsuite>'))
    assert [case["status"] for case in cases] == ["passed", "failure", "error", "skipped"]
    with pytest.raises(HTTPException):
        junit.parse_report(archive('<!DOCTYPE t><testsuite/>'))


def test_scoped_hook_updates_only_its_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "github_get", lambda *a, **kw: {
        "private": False, "id": 1, "owner": {"login": "o"}, "name": "r",
    })
    with TestClient(create_app(tmp_path / "hook.db")) as client:
        ids = []
        for user in ["one", "two"]:
            register(client, user)
            ids.append(client.post("/api/repositories", json={"repository": "o/r"}).json()["id"])
        hook = client.post(f"/api/repositories/{ids[1]}/webhook").json()
        body = json.dumps({"repository": {"id": 1, "private": False}, "workflow_run": RUN}).encode()
        headers = {"X-GitHub-Event": "workflow_run", "X-Hub-Signature-256": "sha256=" +
                   hmac.new(hook["secret"].encode(), body, hashlib.sha256).hexdigest()}
        assert client.post(hook["path"], content=body, headers=headers).status_code == 204
        assert len(client.get(f"/api/repositories/{ids[1]}/dashboard").json()["runs"]) == 1
        client.post("/api/auth/login", json={"username": "one", "password": "test-only-password"})
        assert client.get(f"/api/repositories/{ids[0]}/dashboard").json()["runs"] == []


def test_private_access_checks_session_and_revocation(tmp_path, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    for key in ["CLIENT_ID", "CLIENT_SECRET", "CALLBACK_URL"]:
        monkeypatch.setenv("DEVPULSE_GITHUB_" + key, "test")
    class Grant:
        def raise_for_status(self): pass
        def json(self): return {"access_token": "per-session"}
    monkeypatch.setattr(oauth.httpx2, "post", lambda *a, **kw: Grant())
    info = {"private": True, "id": 1, "owner": {"login": "o"}, "name": "r"}
    monkeypatch.setattr(api, "github_get", lambda *a, **kw: info)
    with TestClient(create_app(tmp_path / "oauth.db")) as client:
        register(client, "private")
        assert client.post("/api/repositories", json={"repository": "o/r"}).status_code == 403
        begin = client.get("/api/auth/github/connect", follow_redirects=False)
        params = parse_qs(urlparse(begin.headers["location"]).query)
        assert params["code_challenge_method"] == ["S256"]
        callback = "/api/auth/github/callback"
        assert client.get(callback, params={"state": "wrong", "code": "code"}).status_code == 403
        query = {"state": params["state"][0], "code": "code"}
        assert client.get(callback, params=query, follow_redirects=False).status_code == 303
        assert client.get(callback, params=query).status_code == 403
        repo = client.post("/api/repositories", json={"repository": "o/r"}).json()
        url = f"/api/repositories/{repo['id']}/dashboard"
        assert client.get(url).status_code == 200
        def revoked(*args, **kwargs):
            assert kwargs["token"] == "per-session"
            raise HTTPException(404)
        monkeypatch.setattr(api, "github_get", revoked)
        assert client.get(url).status_code == 404
        key = token_hash(client.cookies[COOKIE])
        client.post("/api/auth/logout")
        assert client.app.state.github_sessions.token(key) is None
        assert client.post("/api/auth/login", headers={"Origin": "https://elsewhere.example"}).status_code == 403
