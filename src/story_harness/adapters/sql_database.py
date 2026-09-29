"""Shared relational connection and schema migration entry points."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def sqlite_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{Path(path).resolve().as_posix()}"


def open_database(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() not in {"sqlite", "postgresql"}:
        raise ValueError("database must use SQLite or PostgreSQL")
    options = {"poolclass": NullPool} if parsed.get_backend_name() == "sqlite" else {}
    return create_engine(url, pool_pre_ping=True, future=True, **options)


def upgrade_database(url: str) -> None:
    """Migrate a database; serialize PostgreSQL migrations across replicas."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    engine = open_database(url)
    try:
        if engine.dialect.name == "postgresql":
            with engine.connect() as lock:
                lock.execute(text("SELECT pg_advisory_lock(636418255)"))
                lock.commit()
                try:
                    command.upgrade(config, "head")
                finally:
                    lock.execute(text("SELECT pg_advisory_unlock(636418255)"))
                    lock.commit()
        else:
            command.upgrade(config, "head")
    finally:
        engine.dispose()
