"""FastAPI entry point for DevPulse."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import PROJECT_ROOT, create_database_engine, database_path
from .models import Base
from .routers.api import router

logger = logging.getLogger(__name__)


def create_app(db_path: Path | None = None) -> FastAPI:
    """Create the application. Tests can supply their own SQLite file."""
    path = db_path if db_path is not None else database_path()
    engine = create_database_engine(path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
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

    @app.get(
        "/health",
        tags=["System"],
        responses={503: {"description": "Database unavailable"}},
    )
    def health_check() -> dict[str, str]:
        """Check that the service can query SQLite."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("SQLite health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from None

        return {"status": "ok", "database": "ok"}

    app.state.engine = engine
    app.include_router(router)
    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="dashboard")
    return app


app = create_app()
