# DevPulse

DevPulse visualizes GitHub Actions runs and deployment history across public repositories. Open the built-in demo immediately, or create an account to connect and sync a GitHub repository.

## Run locally

Use Python 3.11 or newer. Run these commands from the repository root.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

**macOS or Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload
```

Open the [dashboard](http://127.0.0.1:8000/), [API docs](http://127.0.0.1:8000/docs), or [health check](http://127.0.0.1:8000/health). SQLite creates its data file at `data/devpulse.sqlite3` on startup.

## Monitor a repository

1. Create a DevPulse account using the **Sign in** menu.
2. Choose **Add repository** and enter a public GitHub repository URL or `owner/name`.
3. Choose **Sync GitHub**. A sync reads up to 30 recent runs and five recent deployments, and keeps previously collected records in SQLite.
4. Filter the workflow table or select a run to view the job and step timeline. DevPulse identifies test steps by name, summarizes their outcomes, and links to the full GitHub logs. The test summary counts steps, since workflow job metadata does not contain individual test cases.

Public repository data works without a token, subject to GitHub's unauthenticated API rate limit. Optionally set `DEVPULSE_GITHUB_TOKEN` for higher limits. Use a read-only GitHub credential with Actions, deployments, and repository metadata access. Keep it server-side.

For webhook-driven workflow updates, set `DEVPULSE_WEBHOOK_SECRET` and configure a repository webhook for **Workflow runs** using your HTTPS base URL plus `/api/webhooks/github`. Choose JSON and set the same secret. Deployment history refreshes when you sync.

## Test

```bash
python -m pytest -q -W error
node --check frontend/script.js
```

The automated tests use temporary SQLite databases. They cover health checks, schema startup, authentication, repository isolation, duplicate sync, workflow details, and webhook signatures.

## Docker

Use Docker Compose v2.24 or newer. Copy `.env.example` to `.env` if you need to change settings.

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs -f devpulse
```

The dashboard binds to loopback and stores data in the `devpulse_data` volume.

## GitHub Actions and deployment

[The delivery workflow](.github/workflows/delivery.yml) runs automated tests, builds and smoke-tests the container, and pushes tested `main` images to GHCR with the commit SHA as the tag. Pull requests run tests and the container smoke check.

To enable Linux deployment, provision a server with Docker Compose and SSH access. Configure an HTTPS reverse proxy to forward requests to `127.0.0.1:8000`. Prepare the service environment in `~/devpulse/.env` on the server. Set `DEVPULSE_SECURE_COOKIES=1` for HTTPS and optionally set `DEVPULSE_ALLOW_SIGNUP=0` after creating accounts. If GHCR keeps the package private, authenticate Docker on the server with an account that can read that package.

Create a GitHub environment called `production` with these secrets.

| Secret | Value |
| --- | --- |
| `DEVPULSE_SSH_HOST` | Linux server hostname |
| `DEVPULSE_SSH_USER` | Deployment account with Docker access |
| `DEVPULSE_SSH_KEY` | Private key for that account |
| `DEVPULSE_SSH_KNOWN_HOSTS` | Verified SSH host key line for the target |

Set the repository variable `DEVPULSE_DEPLOY_ENABLED` to `true` after the server is ready. The deployment job pulls the tested image and waits for the container health check. Verify the public dashboard and `/health` through your HTTPS proxy.

## Project layout

| Path | Purpose |
| --- | --- |
| `frontend/` | Dashboard HTML, CSS, and JavaScript |
| `backend/main.py` | App setup, API routing, health check, and static files |
| `backend/database.py`, `backend/models.py` | SQLite and SQLAlchemy schema |
| `backend/auth.py`, `backend/routers/api.py` | Accounts, sessions, repository APIs, and webhooks |
| `backend/services/github.py` | GitHub REST requests and database updates |
| `backend/tests/` | Pytest suite |
| `.github/workflows/delivery.yml` | CI, image publishing, and Linux deployment |
| `Dockerfile`, `docker-compose.yml` | Container image and persistent local service |
