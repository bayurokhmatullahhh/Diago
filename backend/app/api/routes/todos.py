from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.notification import Notification
from app.models.todo import Todo, TodoStatus, utcnow
from app.schemas.todo import TodoCreate, TodoResponse, TodoUpdate

router = APIRouter(prefix="/api/todos", tags=["todos"])


def _database_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=list[TodoResponse], summary="List personal tasks")
def list_todos(
    status_filter: TodoStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[Todo]:
    statement = select(Todo)
    if status_filter is not None:
        statement = statement.where(Todo.status == status_filter)
    statement = statement.order_by(Todo.due_at.is_(None), Todo.due_at, Todo.created_at.desc())
    return list(db.scalars(statement).all())


@router.post(
    "",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a personal task",
)
def create_todo(payload: TodoCreate, db: Session = Depends(get_db)) -> Todo:
    todo = Todo(
        title=payload.title,
        notes=payload.notes,
        due_at=_database_datetime(payload.due_at),
        reminder_at=_database_datetime(payload.reminder_at),
        reminder_revision=1 if payload.reminder_at is not None else 0,
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.patch("/{todo_id}", response_model=TodoResponse, summary="Update a personal task")
def update_todo(
    todo_id: int, payload: TodoUpdate, db: Session = Depends(get_db)
) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field in {"due_at", "reminder_at"}:
            value = _database_datetime(value)
        if field == "reminder_at" and value != todo.reminder_at:
            todo.reminder_revision += 1
            todo.reminder_sent_at = None
        if field == "status":
            todo.completed_at = utcnow() if value == TodoStatus.COMPLETED else None
            if (
                value == TodoStatus.COMPLETED
                and todo.reminder_at is not None
                and todo.reminder_sent_at is None
            ):
                todo.reminder_at = None
                todo.reminder_revision += 1
        setattr(todo, field, value)

    db.commit()
    db.refresh(todo)
    return todo


@router.delete(
    "/{todo_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a personal task"
)
def delete_todo(todo_id: int, db: Session = Depends(get_db)) -> Response:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")
    db.execute(
        update(Notification).where(Notification.todo_id == todo_id).values(todo_id=None)
    )
    db.delete(todo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
