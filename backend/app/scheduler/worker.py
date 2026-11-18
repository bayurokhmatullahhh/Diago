import argparse
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal, init_db
from app.models.notification import Notification
from app.models.todo import Todo, TodoStatus

logger = logging.getLogger("app.scheduler")
DEFAULT_INTERVAL_SECONDS = 15
MAX_REMINDERS_PER_CYCLE = 100


def _database_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def process_due_reminders(
    session_factory: Callable[[], Session],
    now: datetime | None = None,
) -> int:
    """Persist notifications for due reminders exactly once per reminder revision."""
    current_time = _database_utc(now or datetime.now(timezone.utc))
    delivered = 0
    with session_factory() as session:
        due_ids = session.scalars(
            select(Todo.id)
            .where(
                Todo.status == TodoStatus.PENDING,
                Todo.reminder_at.is_not(None),
                Todo.reminder_at <= current_time,
                Todo.reminder_sent_at.is_(None),
            )
            .order_by(Todo.reminder_at, Todo.id)
            .limit(MAX_REMINDERS_PER_CYCLE)
        ).all()

        for todo_id in due_ids:
            todo = session.get(Todo, todo_id)
            if todo is None or todo.reminder_at is None:
                continue

            scheduled_at = _database_utc(todo.reminder_at)
            revision = todo.reminder_revision
            result = session.execute(
                update(Todo)
                .where(
                    Todo.id == todo_id,
                    Todo.status == TodoStatus.PENDING,
                    Todo.title == todo.title,
                    Todo.reminder_at == scheduled_at,
                    Todo.reminder_revision == revision,
                    Todo.reminder_sent_at.is_(None),
                )
                .values(reminder_sent_at=current_time)
            )
            if result.rowcount != 1:
                session.rollback()
                continue

            session.add(
                Notification(
                    todo_id=todo.id,
                    todo_title=todo.title,
                    scheduled_at=scheduled_at,
                    delivered_at=current_time,
                    reminder_revision=revision,
                )
            )
            session.commit()
            delivered += 1
            logger.info("Delivered reminder for todo %s (revision %s)", todo_id, revision)

    return delivered


def run_worker(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db()
    logger.info("Reminder worker started (poll interval: %s seconds)", interval_seconds)

    while True:
        try:
            process_due_reminders(SessionLocal)
        except SQLAlchemyError:
            logger.exception("Reminder worker database operation failed")
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process scheduled Digital Operator reminders.")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Seconds between database polls (default: 15)",
    )
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval must be at least 1 second")
    run_worker(args.interval)


if __name__ == "__main__":
    main()
