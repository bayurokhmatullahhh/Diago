"""Engine & session. Dibuat agar mudah pindah ke PostgreSQL lewat DATABASE_URL."""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_database_url(database_url: str) -> str:
    """Path SQLite relatif dijangkarkan ke root project, bukan ke cwd."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            url = url.set(database=str((PROJECT_ROOT / path).resolve()))
    return url.render_as_string(hide_password=False)


def build_engine(database_url: str) -> Engine:
    database_url = resolve_database_url(database_url)
    url = make_url(database_url)
    kwargs: dict = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, **kwargs)

    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependency FastAPI: satu session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (registrasi model)
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
