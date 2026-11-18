"""Database engine and session handling (SQLite by default, any SQLAlchemy URL works)."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def init_engine(url: str | None = None):
    """Create (or recreate) the engine. Tests call this with a temp database URL."""
    global _engine, _Session
    from . import settings as settings_mod

    url = url or settings_mod.settings.database_url
    if url.startswith("sqlite:///"):
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):  # WAL lets the admin export read while participants write
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(_engine)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def session_scope():
    if _Session is None:
        init_engine()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
