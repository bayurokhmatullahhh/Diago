from app.models import Task, TaskStatus


def test_task_persistence(db_session):
    t = Task(instruction="Pantau website X tiap 10 menit")
    db_session.add(t)
    db_session.commit()

    fetched = db_session.get(Task, t.id)
    assert fetched is not None
    assert fetched.instruction.startswith("Pantau")
    assert fetched.status == TaskStatus.PENDING
    assert fetched.retry_count == 0
    assert fetched.created_at is not None


def test_relative_sqlite_path_anchored_to_project_root():
    from app.db.session import PROJECT_ROOT, resolve_database_url

    resolved = resolve_database_url("sqlite:///./data/x.db")
    assert str(PROJECT_ROOT) in resolved
    assert resolve_database_url("sqlite://") == "sqlite://"
