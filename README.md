# DevPulse

DevPulse visualizes GitHub Actions runs and deployment history across public repositories. A configured GitHub App also supports private repository monitoring. Open the built-in demo or create an account to connect a repository.

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
3. Choose **Sync GitHub**. A sync reads up to 30 recent runs and five recent GitHub deployment records, and preserves previously collected records in the configured database. Historical failures stay visible in the workflow table and notification feed.
4. Filter the workflow table or select a run to view the job and step timeline. DevPulse identifies test steps by name, summarizes their outcomes, and links to the full GitHub logs. The test summary counts steps, since workflow job metadata does not contain individual test cases.

Public repository data works without a token, subject to GitHub's unauthenticated API rate limit. Optionally set `DEVPULSE_GITHUB_TOKEN` for higher limits. Use a read-only GitHub credential with Actions, deployments, and repository metadata access. Keep it server-side.

**View individual test results** requires a GitHub Actions artifact named `devpulse-junit-<attempt>` containing `junit.xml`. GitHub requires a credential with Actions read access to download the report even for public repositories. For public repositories, set `DEVPULSE_GITHUB_TOKEN` on the server. For private repositories, use the authorized GitHub App connection. Workflow summaries and links to logs remain available when the report is unavailable.

The **Workflow performance** chart shows daily average run duration and pass rate for the latest seven active days in UTC. Pass rate counts successful and failed runs. The chart also has a data table.

The in-app notification feed shows workflow failures and successful deployments for the selected repository. Open dashboards refresh saved data every 15 seconds. To receive updates between manual syncs, set `DEVPULSE_WEBHOOK_SECRET` and configure a repository webhook for **Workflow runs** and **Deployment statuses** using your HTTPS base URL plus `/api/webhooks/github`. Choose JSON and set the same secret.

### Track a workflow failure

1. Sign in, select a connected repository, and sync GitHub.
2. Open a completed failed run from **Action needed** or **Recent workflows**. Use **All saved runs** if the failure is outside the default time range.
3. In **Failure investigation**, choose **Load investigation**. Set the status to **Investigating**, enter a probable cause and optionally add notes, then save.
4. After confirming the fix, add a resolution note and save the status as **Resolved**. The run leaves **Action needed** and stays marked **Failed** in GitHub and in workflow history. Select **Open** to reopen the investigation.

Each connected repository stores a separate investigation for each failed attempt. It belongs to your DevPulse account and survives syncs and restarts with a persistent database. The demo workspace shows where investigations appear. A connected repository is required to save one.

The [UX coursework notes](docs/ux-coursework.md) map the seven screens to app interactions and include a usability test plan.

## Test

```bash
python -m pytest -q -W error
node --check frontend/script.js
```

The automated tests cover health checks, schema startup, authentication, repository isolation, duplicate sync, workflow details, and webhook signatures using temporary SQLite databases. CI also tests persistence across app restarts with a disposable PostgreSQL service. Set `DEVPULSE_TEST_POSTGRES_URL` to a dedicated test database to run that test locally.

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

### Render

For an existing image-backed Render service, connect a PostgreSQL database before enabling automatic deployments if account and repository history need to survive restarts. Set `DEVPULSE_DATABASE_URL` in the service environment to the database's direct connection URL, using the provider's TLS settings, and set `DEVPULSE_SECURE_COOKIES=1` for HTTPS. The app initializes the schema on startup. This starts with the configured database's contents. Back up and migrate any SQLite data that still needs to be retained before switching. Render Free uses an ephemeral filesystem, and its free PostgreSQL databases expire after 30 days.

1. Copy the service's deploy hook from its Render settings into the GitHub **production** environment secret `DEVPULSE_RENDER_DEPLOY_HOOK`. Treat the hook as a credential.
2. Set the repository variable `DEVPULSE_RENDER_URL` to the service's HTTPS `onrender.com` URL and `DEVPULSE_DEPLOY_TARGET` to `render`.
3. Push to `main` or run **CI and delivery** from GitHub Actions. The job requests the exact published image and checks that the healthy public instance reports the matching commit. GitHub records the result on the production environment.

### Self-hosted Linux

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
| `backend/database.py`, `backend/models.py` | SQLite and PostgreSQL connections and SQLAlchemy schema |
| `backend/auth.py`, `backend/routers/api.py` | Accounts, sessions, repository APIs, and webhooks |
| `backend/services/github.py` | GitHub REST requests and database updates |
| `backend/tests/` | Pytest suite |
| `.github/workflows/delivery.yml` | CI, image publishing, and Render or Linux deployment |
| `Dockerfile`, `docker-compose.yml` | Container image and persistent local service |

## Monitoring and operations

Use Repository portfolio, Check release readiness and Analyze test stability above Overview. Failed run details also offer comparison with the previous successful run. See [release investigation guide](docs/release-insights.md) for evidence limits and demonstration steps.

See [operator instructions](docs/operations.md) for JUnit reports, repository webhooks, private GitHub access and PostgreSQL recovery. The [UX study kit](docs/ux-coursework.md) includes editable design frames and a participant worksheet.
