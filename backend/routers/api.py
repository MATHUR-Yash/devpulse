"""Account, repository, run, deployment, and webhook endpoints."""

import hashlib
import hmac
import os
import re
import secrets
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..auth import COOKIE, SESSION_AGE, current_user, password_hash, token_hash, utc_now, verify_password
from ..database import insert_for
from ..services.junit import read_cases
from ..services.oauth import session_id
from ..models import RepositoryHook, PrivateRepository
from ..models import SavedTestReport
from ..services.insights import FAILURES, readiness, test_signals
from ..models import BrowserSession, GitHubDeployment, Repository, SyncHistory, User, WorkflowRun
from ..services.github import (
    collect_deployments, deployment_values, github_get, repository_path, save_deployment, save_run,
)

router = APIRouter(prefix="/api")
REPO_PATTERN = re.compile(r"([A-Za-z0-9-]{1,39})/([A-Za-z0-9_.-]{1,100})")


def get_db(request: Request):
    with Session(request.app.state.engine) as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class Registration(Credentials):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RepositoryInput(BaseModel):
    repository: str = Field(min_length=3, max_length=155)


def open_session(db: Session, user: User, response: Response) -> dict:
    token = secrets.token_urlsafe(32)
    db.execute(delete(BrowserSession).where(BrowserSession.expires_at <= utc_now()))
    db.add(BrowserSession(token_hash=token_hash(token), user=user, expires_at=utc_now() + SESSION_AGE))
    db.commit()
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_AGE.total_seconds()), httponly=True,
        samesite="lax", secure=os.getenv("DEVPULSE_SECURE_COOKIES") == "1" or bool(os.getenv("RENDER")),
    )
    return {"username": user.username}


@router.post("/auth/register", status_code=201)
def register(data: Registration, response: Response, db: DB):
    if os.getenv("DEVPULSE_ALLOW_SIGNUP", "1") != "1":
        raise HTTPException(403, "Registration is disabled.")
    user = User(username=data.username.lower(), email=data.email.lower(), password_hash=password_hash(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This username or email is already registered.") from None
    return open_session(db, user, response)


@router.post("/auth/login")
def login(data: Credentials, response: Response, db: DB):
    user = db.scalar(select(User).where(User.username == data.username.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Username or password is incorrect.")
    return open_session(db, user, response)


@router.get("/auth/me")
def me(request: Request, db: DB):
    return {"username": current_user(request, db).username,
            "github_configured": all(os.getenv("DEVPULSE_GITHUB_" + key)
                                     for key in ("CLIENT_ID", "CLIENT_SECRET", "CALLBACK_URL"))}


@router.get("/auth/github/connect")
def github_connect(request: Request, db: DB):
    current_user(request, db)
    return request.app.state.github_sessions.begin(session_id(request))


@router.get("/auth/github/callback")
def github_callback(request: Request, db: DB, code: str, state: str):
    current_user(request, db)
    return request.app.state.github_sessions.finish(session_id(request), code, state)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: DB):
    if token := request.cookies.get(COOKIE):
        request.app.state.github_sessions.forget(token_hash(token))
        db.execute(delete(BrowserSession).where(BrowserSession.token_hash == token_hash(token)))
        db.commit()
    response.delete_cookie(COOKIE)


def repo_data(repo: Repository) -> dict:
    return {"id": repo.id, "name": f"{repo.owner}/{repo.name}"}


def own_repo(db: Session, request: Request, repository_id: int) -> Repository:
    user = current_user(request, db)
    repo = db.get(Repository, repository_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(404, "Repository is not connected to this account.")
    return repo


def repository_access(repo, request, db, *, verify_public=True):
    private = db.get(PrivateRepository, repo.id) is not None
    token = request.app.state.github_sessions.token(session_id(request)) if private else None
    if private and not token:
        raise HTTPException(403, "Connect your GitHub account to access this private repository.")
    if private or verify_public:
        info = github_get(repository_path(repo), token=token)
        if info["id"] != repo.github_repo_id or (info["private"] and not token):
            raise HTTPException(403, "Repository identity or visibility changed. Reconnect it.")
    return token


@router.get("/repositories")
def repositories(request: Request, db: DB):
    user = current_user(request, db)
    rows = db.scalars(select(Repository).where(Repository.user_id == user.id).order_by(Repository.name))
    return [repo_data(repo) for repo in rows]


@router.post("/repositories", status_code=201)
def connect_repository(data: RepositoryInput, request: Request, db: DB):
    user_id = current_user(request, db).id
    name = data.repository.strip().rstrip("/").removeprefix("https://github.com/").removesuffix(".git")
    if not REPO_PATTERN.fullmatch(name) or name.split("/")[1] in {".", ".."}:
        raise HTTPException(422, "Enter a GitHub repository as owner/name.")
    db.rollback()
    token = request.app.state.github_sessions.token(session_id(request))
    info = github_get(f"/repos/{name}", token=token)
    if info["private"] and not token:
        raise HTTPException(403, "Connect your GitHub account to monitor private repositories.")
    stmt = insert_for(db, Repository).values(
        user_id=user_id, github_repo_id=info["id"], owner=info["owner"]["login"], name=info["name"]
    )
    db.execute(stmt.on_conflict_do_update(
        index_elements=["user_id", "github_repo_id"],
        set_={"owner": stmt.excluded.owner, "name": stmt.excluded.name},
    ))
    row = db.scalar(select(Repository).where(Repository.user_id == user_id, Repository.github_repo_id == info["id"]))
    result = repo_data(row)
    if info["private"]:
        db.merge(PrivateRepository(repository_id=row.id))
    db.commit()
    return result


@router.post("/repositories/{repository_id}/sync")
def sync(repository_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    base = repository_path(repo)
    try:
        # Recheck visibility when repositories change after being connected.
        token = repository_access(repo, request, db)
        db.rollback()
        runs = github_get(f"{base}/actions/runs", token=token, per_page=30)["workflow_runs"]
        deployments = collect_deployments(base, token=token)
    except HTTPException:
        db.add(SyncHistory(repository_id=repository_id, status="failure"))
        db.commit()
        raise
    for run in runs:
        save_run(db, repository_id, run)
    for deployment in deployments:
        save_deployment(db, repository_id, deployment)
    db.add(SyncHistory(repository_id=repository_id, status="success"))
    db.commit()
    return {"runs": len(runs), "deployments": len(deployments)}


def utc_iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


@router.get("/repositories/{repository_id}/dashboard")
def dashboard(repository_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    repository_access(repo, request, db, verify_public=False)
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.repository_id == repository_id)
        .order_by(WorkflowRun.github_run_id.desc(), WorkflowRun.run_attempt.desc()).limit(100)).all()
    deployments = db.scalars(select(GitHubDeployment).where(GitHubDeployment.repository_id == repository_id)
        .order_by(GitHubDeployment.updated_at.desc()).limit(30))
    last_sync = db.scalar(select(SyncHistory).where(SyncHistory.repository_id == repository_id)
        .order_by(SyncHistory.id.desc()).limit(1))
    return {
        "runs": [{
            "id": run.id, "name": run.workflow_name, "attempt": run.run_attempt,
            "branch": run.branch, "sha": run.commit_sha, "status": run.status,
            "conclusion": run.conclusion, "started_at": utc_iso(run.started_at),
            "completed_at": utc_iso(run.completed_at),
        } for run in runs],
        "deployments": [{
            "id": item.github_id, "environment": item.environment, "version": item.version,
            "sha": item.commit_sha, "status": item.status, "updated_at": utc_iso(item.updated_at),
        } for item in deployments],
        "last_sync": {"at": utc_iso(last_sync.synced_at), "status": last_sync.status} if last_sync else None,
    }


@router.get("/repositories/{repository_id}/runs/{run_id}")
def run_details(repository_id: int, run_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    base = repository_path(repo)
    run = db.get(WorkflowRun, run_id)
    if run is None or run.repository_id != repository_id:
        raise HTTPException(404, "Workflow run was not found.")
    github_id, attempt = run.github_run_id, run.run_attempt
    token = repository_access(repo, request, db)
    db.rollback()
    jobs = github_get(f"{base}/actions/runs/{github_id}/attempts/{attempt}/jobs", token=token, per_page=100)
    return {"url": f"https://github.com{base.removeprefix('/repos')}/actions/runs/{github_id}", "jobs": [{
        "name": job["name"], "status": job["status"], "conclusion": job.get("conclusion"),
        "started_at": job.get("started_at"), "completed_at": job.get("completed_at"),
        "steps": job.get("steps") or [],
    } for job in jobs["jobs"]]}


@router.get("/repositories/{repository_id}/runs/{run_id}/tests")
def test_report(repository_id: int, run_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    base = repository_path(repo)
    run = db.get(WorkflowRun, run_id)
    if run is None or run.repository_id != repo.id:
        raise HTTPException(404, "Workflow run was not found.")
    github_id, attempt = run.github_run_id, run.run_attempt
    token = repository_access(repo, request, db)
    db.rollback()
    return saved_report(db, run, base, token)


def saved_report(db, run, base, token):
    saved = db.get(SavedTestReport, run.id)
    if saved:
        return {"available": True, "cases": saved.cases}
    report = read_cases(base, run.github_run_id, run.run_attempt, token)
    if report["available"] and run.status == "completed":
        stmt = insert_for(db, SavedTestReport).values(run_id=run.id, cases=report["cases"])
        db.execute(stmt.on_conflict_do_nothing(index_elements=["run_id"]))
        db.commit()
    return report


def run_summary(run):
    return {"id": run.id, "name": run.workflow_name, "sha": run.commit_sha,
            "branch": run.branch, "attempt": run.run_attempt, "conclusion": run.conclusion}


@router.get("/repositories/{repository_id}/runs/{run_id}/comparison")
def compare_failure(repository_id: int, run_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    token = repository_access(repo, request, db)
    run = db.get(WorkflowRun, run_id)
    if not run or run.repository_id != repo.id:
        raise HTTPException(404, "Workflow run was not found.")
    if run.conclusion not in FAILURES:
        raise HTTPException(422, "Choose a failed workflow to compare.")
    candidates = db.scalars(select(WorkflowRun).where(
        WorkflowRun.repository_id == repo.id, WorkflowRun.workflow_name == run.workflow_name,
        WorkflowRun.branch == run.branch, WorkflowRun.conclusion == "success",
    ).order_by(WorkflowRun.github_run_id.desc(), WorkflowRun.run_attempt.desc())).all()
    baseline = next((r for r in candidates if (r.github_run_id, r.run_attempt) <
                     (run.github_run_id, run.run_attempt)), None)
    base = repository_path(repo)
    def jobs_for(item):
        return github_get(f"{base}/actions/runs/{item.github_run_id}/attempts/{item.run_attempt}/jobs",
                          token=token, per_page=100)["jobs"]
    jobs = jobs_for(run)
    failed = [{"job": job["name"], "step": step["name"]} for job in jobs
              for step in job.get("steps", []) if step.get("conclusion") in FAILURES]
    return {"failed": run_summary(run), "baseline": run_summary(baseline) if baseline else None,
            "failed_steps": failed, "first_failure": failed[0] if failed else None,
            "baseline_jobs": [{"name": j["name"], "conclusion": j.get("conclusion")} for j in jobs_for(baseline)] if baseline else [],
            "compare_url": f"https://github.com/{repo.owner}/{repo.name}/compare/{baseline.commit_sha}...{run.commit_sha}" if baseline else None}


@router.get("/repositories/{repository_id}/runs/{run_id}/test-history")
def test_history(repository_id: int, run_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    token = repository_access(repo, request, db)
    selected = db.get(WorkflowRun, run_id)
    if not selected or selected.repository_id != repo.id:
        raise HTTPException(404, "Workflow run was not found.")
    runs = db.scalars(select(WorkflowRun).where(
        WorkflowRun.repository_id == repo.id, WorkflowRun.workflow_name == selected.workflow_name,
        WorkflowRun.branch == selected.branch, WorkflowRun.status == "completed",
        or_(WorkflowRun.github_run_id < selected.github_run_id,
            and_(WorkflowRun.github_run_id == selected.github_run_id,
                 WorkflowRun.run_attempt <= selected.run_attempt)),
    ).order_by(WorkflowRun.github_run_id.desc(), WorkflowRun.run_attempt.desc()).limit(5)).all()
    reports, missing = [], []
    for run in runs:
        try:
            report = saved_report(db, run, repository_path(repo), token)
            if report["available"]:
                reports.append((run, report["cases"]))
            else:
                missing.append({"run_id": run.id, "reason": "No retained JUnit artifact"})
        except HTTPException as error:
            missing.append({"run_id": run.id, "reason": error.detail})
    return {"workflow": selected.workflow_name, "branch": selected.branch, "examined": len(runs),
            "reports_available": len(reports), "missing": missing, "candidates": test_signals(reports)}


@router.get("/repositories/{repository_id}/readiness")
def release_readiness(repository_id: int, request: Request, db: DB):
    repo = own_repo(db, request, repository_id)
    token = repository_access(repo, request, db)
    base = repository_path(repo)
    info = github_get(base, token=token)
    branch = info["default_branch"]
    from urllib.parse import quote
    head = github_get(f"{base}/commits/{quote(branch, safe='')}", token=token)["sha"]
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.repository_id == repo.id,
        WorkflowRun.branch == branch).order_by(WorkflowRun.github_run_id.desc(), WorkflowRun.run_attempt.desc()).limit(100)).all()
    latest = {}
    for run in runs:
        if run.commit_sha == head:
            latest.setdefault(run.github_run_id, run)
    reports, missing = [], []
    for run in list(latest.values())[:5]:
        if run.status != "completed":
            continue
        try:
            report = saved_report(db, run, base, token)
            if report["available"]:
                reports.append(report["cases"])
            else:
                missing.append(run.id)
        except HTTPException:
            missing.append(run.id)
    # GitHub can mark older deployments inactive after a new release succeeds.
    # Their status timestamp must not make them the newest deployment.
    deployments = db.scalars(select(GitHubDeployment).where(GitHubDeployment.repository_id == repo.id)
        .order_by(GitHubDeployment.github_id.desc())).all()
    return {**readiness(runs, reports, deployments, head), "branch": branch,
            "missing_reports": missing, "checked_at": utc_iso(utc_now()),
            "scope": "Saved default-branch runs for the live head. JUnit sampled from up to five runs. Deployment environment: production."}


@router.get("/portfolio")
def portfolio(request: Request, db: DB):
    user = current_user(request, db)
    repos = db.scalars(select(Repository).where(Repository.user_id == user.id).order_by(Repository.name)).all()
    result = []
    for repo in repos:
        try:
            data = dashboard(repo.id, request, db)
            runs = data["runs"]
            result.append({"id": repo.id, "name": f"{repo.owner}/{repo.name}", "accessible": True,
                "latest": runs[0] if runs else None, "run_count": len(runs),
                "failed": sum(r["conclusion"] in FAILURES for r in runs),
                "deployment": data["deployments"][0] if data["deployments"] else None,
                "last_sync": data["last_sync"]})
        except HTTPException:
            result.append({"id": repo.id, "name": f"{repo.owner}/{repo.name}", "accessible": False})
    return {"repositories": result}


@router.post("/repositories/{repository_id}/webhook")
def generate_webhook(repository_id: int, request: Request, db: DB):
    own_repo(db, request, repository_id)
    secret = secrets.token_urlsafe(32)
    db.merge(RepositoryHook(repository_id=repository_id, secret=secret))
    db.commit()
    return {"path": f"/api/webhooks/github/{repository_id}", "secret": secret}


def apply_webhook(engine, event: str, payload: dict, target: int | None = None) -> None:
    repository = payload.get("repository", {})
    if repository.get("private") is not False or not repository.get("id"):
        return
    run = payload.get("workflow_run") if event == "workflow_run" else None
    deployment = payload.get("deployment") if event == "deployment_status" else None
    status = payload.get("deployment_status")
    if not run and not (deployment and status):
        return
    with Session(engine) as db:
        query = select(Repository.id).where(Repository.github_repo_id == repository["id"])
        if target is not None:
            query = query.where(Repository.id == target)
        repo_ids = db.scalars(query).all()
        for repository_id in repo_ids:
            if run:
                save_run(db, repository_id, run)
            else:
                save_deployment(db, repository_id, deployment_values(deployment, status))
        db.commit()


def hook_secret(engine, target):
    with Session(engine) as db:
        return db.scalar(select(RepositoryHook.secret).where(RepositoryHook.repository_id == target))


@router.post("/webhooks/github", status_code=204)
@router.post("/webhooks/github/{repository_id}", status_code=204)
async def webhook(request: Request, repository_id: int | None = None):
    secret = (await run_in_threadpool(hook_secret, request.app.state.engine, repository_id)
              if repository_id is not None else os.getenv("DEVPULSE_WEBHOOK_SECRET"))
    if not secret:
        raise HTTPException(503, "GitHub webhooks are disabled.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2 * 1024 * 1024:
            raise HTTPException(413, "Webhook exceeds 2 MiB.")
        body.extend(chunk)
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(403, "Invalid webhook signature.")
    event = request.headers.get("X-GitHub-Event")
    if event in {"workflow_run", "deployment_status"}:
        import json
        try:
            payload = json.loads(body)
            await run_in_threadpool(apply_webhook, request.app.state.engine, event, payload, repository_id)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(422, "Invalid GitHub event.") from None
