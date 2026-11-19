"""Initial schema for accounts, repositories, and pipeline history."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for the SQLAlchemy models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    repositories: Mapped[list["Repository"]] = relationship(back_populates="user")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_repo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    github_repo_id: Mapped[int] = mapped_column(BigInteger)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="repositories")
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="repository")
    deployments: Mapped[list["Deployment"]] = relationship(back_populates="repository")
    sync_records: Mapped[list["SyncHistory"]] = relationship(back_populates="repository")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_run_id", "run_attempt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    github_run_id: Mapped[int] = mapped_column(BigInteger)
    run_attempt: Mapped[int] = mapped_column(default=1, server_default="1")
    workflow_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    conclusion: Mapped[str | None] = mapped_column(String(32))
    branch: Mapped[str | None] = mapped_column(String(255))
    commit_sha: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    repository: Mapped[Repository] = relationship(back_populates="workflow_runs")


class RepositoryHook(Base):
    __tablename__ = "repository_hooks"
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    secret: Mapped[str] = mapped_column(String(100))


class PrivateRepository(Base):
    __tablename__ = "private_repositories"
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)


class SavedTestReport(Base):
    __tablename__ = "saved_test_reports"
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), primary_key=True)
    cases: Mapped[list] = mapped_column(JSON)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    version: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime)

    repository: Mapped[Repository] = relationship(back_populates="deployments")


class SyncHistory(Base):
    __tablename__ = "sync_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(32))

    repository: Mapped[Repository] = relationship(back_populates="sync_records")


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    user: Mapped[User] = relationship()


class GitHubDeployment(Base):
    __tablename__ = "github_deployments"
    __table_args__ = (UniqueConstraint("repository_id", "github_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    github_id: Mapped[int] = mapped_column(BigInteger)
    environment: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(255))
    commit_sha: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
