from __future__ import annotations

from collections.abc import Iterator
from functools import cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from autoeng.settings import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[3]


@cache
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


@cache
def _factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(get_engine(url), expire_on_commit=False)


def session_scope() -> Session:
    return _factory()()


def get_db() -> Iterator[Session]:
    db = session_scope()
    try:
        yield db
    finally:
        db.close()


def migrate() -> None:
    """Bring the database schema up to date (alembic upgrade head)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging configuration
    command.upgrade(cfg, "head")
