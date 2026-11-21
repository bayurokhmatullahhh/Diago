from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


def _upgrade(database_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_migration_creates_schema_for_new_database(tmp_path):
    database_path = tmp_path / "new.db"
    _upgrade(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("todos")}
        assert {
            "reminder_at",
            "reminder_revision",
            "reminder_sent_at",
            "project_id",
            "priority",
        } <= columns
        assert "notifications" in inspector.get_table_names()
        assert "projects" in inspector.get_table_names()
        assert {"chat_conversations", "agent_actions"} <= set(inspector.get_table_names())
    finally:
        engine.dispose()


def test_migration_preserves_existing_todos(tmp_path):
    database_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE todos ("
                    "id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, "
                    "notes TEXT, due_at DATETIME, status VARCHAR(9) NOT NULL, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                    "completed_at DATETIME)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO todos (id, title, status, created_at, updated_at) "
                    "VALUES (1, 'Existing task', 'PENDING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    _upgrade(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT title, reminder_revision, priority FROM todos WHERE id = 1")
            ).one()
            assert row == ("Existing task", 0, "normal")
            assert inspect(connection).get_foreign_keys("todos")[0]["referred_table"] == "projects"
            assert "notifications" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
