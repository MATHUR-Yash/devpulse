"""Read GitHub Actions and deployment data without exposing credentials."""

import os
from datetime import datetime, timezone

import httpx2
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models import GitHubDeployment, Repository, WorkflowRun


def github_get(path: str, **params):
    token = os.getenv("DEVPULSE_GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx2.get(
            f"https://api.github.com{path}", params=params, headers=headers, timeout=10
        )
        response.raise_for_status()
    except httpx2.HTTPStatusError as error:
        status = error.response.status_code
        if status == 404:
            raise HTTPException(404, "GitHub could not find this repository or record.") from None
        if status in {403, 429}:
            raise HTTPException(503, "GitHub denied access or reached its API rate limit.") from None
        raise HTTPException(502, "GitHub rejected the request. Check the server token.") from None
    except httpx2.RequestError:
        raise HTTPException(502, "DevPulse could not reach GitHub.") from None
    return response.json()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


def repository_path(repo: Repository) -> str:
    return f"/repos/{repo.owner}/{repo.name}"


def collect_deployments(base: str) -> list[dict]:
    deployments = github_get(f"{base}/deployments", per_page=5)
    results = []
    for item in deployments:
        updates = github_get(f"{base}/deployments/{item['id']}/statuses", per_page=1)
        latest = updates[0] if updates else {}
        results.append({
            "github_id": item["id"],
            "environment": item["environment"],
            "version": item.get("ref") or item["sha"],
            "commit_sha": item["sha"],
            "status": latest.get("state", "pending"),
            "updated_at": parse_time(latest.get("created_at") or item["created_at"]),
        })
    return results


def save_run(db: Session, repository_id: int, run: dict) -> None:
    values = {
        "repository_id": repository_id,
        "github_run_id": run["id"],
        "run_attempt": run.get("run_attempt") or 1,
        "workflow_name": run.get("name") or "Workflow",
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "branch": run.get("head_branch"),
        "commit_sha": run["head_sha"],
        "started_at": parse_time(run.get("run_started_at")),
        "completed_at": parse_time(run.get("updated_at")) if run["status"] == "completed" else None,
    }
    stmt = insert(WorkflowRun).values(**values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=["repository_id", "github_run_id", "run_attempt"],
        set_={key: stmt.excluded[key] for key in values if key != "repository_id"},
        where=or_(
            WorkflowRun.status != "completed",
            (stmt.excluded.status == "completed") & (
                (WorkflowRun.completed_at.is_(None))
                | (stmt.excluded.completed_at >= WorkflowRun.completed_at)
            ),
        ),
    ))


def save_deployment(db: Session, repository_id: int, values: dict) -> None:
    stmt = insert(GitHubDeployment).values(repository_id=repository_id, **values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=["repository_id", "github_id"],
        set_={key: stmt.excluded[key] for key in values if key != "github_id"},
        where=stmt.excluded.updated_at >= GitHubDeployment.updated_at,
    ))
