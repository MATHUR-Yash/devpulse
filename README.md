# DevPulse

DevPulse is a CI/CD pipeline monitoring and deployment management dashboard in development. This first phase provides a FastAPI service, a local SQLite database, and the initial SQLAlchemy schema.

## Project layout

```text
devpulse/
├── .github/workflows/    # GitHub Actions workflow directory
├── backend/
│   ├── __init__.py       # Python package marker
│   ├── main.py           # FastAPI startup and GET /health
│   ├── database.py       # SQLite path and SQLAlchemy engine
│   ├── models.py         # Tables, foreign keys, and relationships
│   ├── routers/          # Future API modules
│   ├── services/         # Future GitHub and pipeline logic
│   └── tests/            # Pytest coverage for the API and schema
├── frontend/             # Future HTML, CSS, and JavaScript
├── .env.example          # Optional database path example
├── .gitignore
├── requirements.txt     # Runtime and test dependencies
└── README.md
```

## Set up and run

Use Python 3.11 or newer and run the commands from the project root.

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

Open [GET /health](http://127.0.0.1:8000/health). A successful check returns HTTP 200 with this body.

```json
{"status": "ok", "database": "ok"}
```

If SQLite becomes unavailable while the service is running, the endpoint returns HTTP 503. The interactive API explorer is available at [/docs](http://127.0.0.1:8000/docs). Stop the server with Ctrl+C.

## Database

FastAPI creates `data/devpulse.sqlite3` and its tables on startup. To use a different location, set the optional `DEVPULSE_DB_PATH` environment variable before starting the server. In PowerShell, use `$env:DEVPULSE_DB_PATH = 'data/local.sqlite3'`. In Bash, use `export DEVPULSE_DB_PATH=data/local.sqlite3`. Relative paths resolve from the project root. The `.env.example` file serves as a reference.

| Model | Table | Records |
| --- | --- | --- |
| `User` | `users` | Accounts with a password hash field |
| `Repository` | `repositories` | GitHub repositories connected by a user |
| `WorkflowRun` | `workflow_runs` | Workflow attempts, statuses, conclusions, and timestamps |
| `Deployment` | `deployments` | Versions, deployment statuses, and timestamps |
| `SyncHistory` | `sync_history` | Repository sync outcomes and timestamps |

Each user can connect multiple repositories. Repositories own their workflow runs, deployments, and sync records. Store timestamps in UTC. Startup creates missing tables. Changes to existing tables will need a migration once the schema evolves.

## Run tests

Run `python -m pytest` with your virtual environment active. If you used its Python executable directly during setup, use `.\.venv\Scripts\python.exe -m pytest` on Windows or `.venv/bin/python -m pytest` on macOS or Linux. Tests use temporary SQLite files.

## Later phases

The planned dashboard, authentication, GitHub repository sync, and pipeline views will build on this foundation. GitHub Actions workflows belong in `.github/workflows/`. The future `Dockerfile` and `docker-compose.yml` will live in the project root alongside the GHCR publishing and deployment setup.
