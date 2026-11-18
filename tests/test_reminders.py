from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification
from app.models.todo import Todo, TodoStatus
from app.scheduler.worker import process_due_reminders


def test_worker_delivers_due_reminders_once_and_skips_completed(db_session):
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    due = Todo(
        title="Due reminder",
        reminder_at=now - timedelta(minutes=1),
        reminder_revision=1,
    )
    future = Todo(
        title="Future reminder",
        reminder_at=now + timedelta(minutes=1),
        reminder_revision=1,
    )
    completed = Todo(
        title="Completed reminder",
        reminder_at=now - timedelta(minutes=2),
        reminder_revision=1,
        status=TodoStatus.COMPLETED,
    )
    db_session.add_all([due, future, completed])
    db_session.commit()
    due_id = due.id

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert process_due_reminders(factory, now) == 1
    assert process_due_reminders(factory, now) == 0

    reminders = db_session.scalars(select(Notification)).all()
    assert len(reminders) == 1
    assert reminders[0].todo_id == due_id
    assert reminders[0].todo_title == "Due reminder"
    assert reminders[0].is_read is False
    db_session.refresh(due)
    db_session.refresh(future)
    db_session.refresh(completed)
    assert db_session.get(Todo, due_id).reminder_sent_at is not None
    assert db_session.get(Todo, future.id).reminder_sent_at is None
    assert db_session.get(Todo, completed.id).reminder_sent_at is None


def test_notification_api_lists_and_marks_notifications_read(client, db_session):
    created = client.post(
        "/api/todos",
        json={
            "title": "Reminder inbox",
            "reminder_at": "2026-11-10T11:59:00Z",
        },
    ).json()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert process_due_reminders(
        factory, datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    ) == 1

    listing = client.get("/api/notifications")
    assert listing.status_code == 200
    body = listing.json()
    assert body["unread_count"] == 1
    assert body["items"][0]["todo_id"] == created["id"]
    assert body["items"][0]["todo_title"] == "Reminder inbox"

    notification_id = body["items"][0]["id"]
    marked = client.patch(f"/api/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert client.get("/api/notifications").json()["unread_count"] == 0
    assert client.patch("/api/notifications/read-all").json() == {"updated": 0}
    assert client.delete(f"/api/todos/{created['id']}").status_code == 204
    retained = client.get("/api/notifications").json()["items"][0]
    assert retained["todo_id"] is None
    assert retained["todo_title"] == "Reminder inbox"
    assert client.patch("/api/notifications/999/read").status_code == 404
