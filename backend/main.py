"""FastAPI entry point for DevPulse."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from collections import deque
from time import monotonic
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import PROJECT_ROOT, create_database_engine, create_postgres_engine, database_path
from .models import Base
from .routers.api import router
from .services.oauth import GitHubSessions

logger = logging.getLogger(__name__)


def create_app(db_path: Path | None = None) -> FastAPI:
    """Create the application, using SQLite unless a PostgreSQL URL is set."""
    url = os.getenv("DEVPULSE_DATABASE_URL") if db_path is None else None
    if url:
        path = None
        engine = create_postgres_engine(url)
    else:
        path = db_path if db_path is not None else database_path()
        engine = create_database_engine(path)
    revision = os.getenv("DEVPULSE_REVISION")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="DevPulse",
        description="CI/CD pipeline monitoring and deployment management.",
        version="1.0.0",
        lifespan=lifespan,
    )

    attempts = {}

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        path = request.url.path
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin not in {
            str(request.base_url).rstrip("/"), os.getenv("RENDER_EXTERNAL_URL"),
        }:
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
        if path in {"/api/auth/login", "/api/auth/register"} and request.method == "POST":
            now = monotonic()
            address = request.client.host if request.client else "unknown"
            for key in list(attempts):
                if attempts[key][-1] <= now - 60:
                    del attempts[key]
            recent = attempts.setdefault(address, deque())
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= 20:
                return JSONResponse({"detail": "Try again in one minute."}, status_code=429,
                                    headers={"Retry-After": "60"})
            recent.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get(
        "/health",
        tags=["System"],
        responses={503: {"description": "Database unavailable"}},
    )
    def health_check(response: Response) -> dict[str, str]:
        """Check the database and identify the running image when built by CI."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from None

        response.headers["Cache-Control"] = "no-store"
        if revision:
            response.headers["X-DevPulse-Revision"] = revision
        return {"status": "ok", "database": "ok"}

    app.state.engine = engine
    app.state.github_sessions = GitHubSessions()
    app.include_router(router)
    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="dashboard")
    return app


app = create_app()
