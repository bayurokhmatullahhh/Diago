from datetime import datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models.todo import TodoPriority, TodoStatus


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Datetime harus menyertakan timezone, misalnya Z atau +07:00")
    return value.astimezone(timezone.utc) if value is not None else None


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    project_id: int | None = Field(default=None, ge=1)
    priority: TodoPriority = TodoPriority.NORMAL
    due_at: datetime | None = None
    reminder_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Judul tidak boleh kosong")
        return value.strip()

    @field_validator("due_at")
    @classmethod
    def due_at_requires_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)

    @field_validator("reminder_at")
    @classmethod
    def reminder_at_requires_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    project_id: int | None = Field(default=None, ge=1)
    priority: TodoPriority | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    status: TodoStatus | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            if not value.strip():
                raise ValueError("Judul tidak boleh kosong")
            return value.strip()
        return value

    @field_validator("due_at")
    @classmethod
    def due_at_requires_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)

    @field_validator("reminder_at")
    @classmethod
    def reminder_at_requires_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TodoUpdate":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Judul tidak boleh null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Status tidak boleh null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Prioritas tidak boleh null")
        return self


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    notes: str | None
    project_id: int | None
    priority: TodoPriority
    due_at: datetime | None
    reminder_at: datetime | None
    reminder_sent_at: datetime | None
    status: TodoStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @field_serializer(
        "due_at",
        "reminder_at",
        "reminder_sent_at",
        "created_at",
        "updated_at",
        "completed_at",
    )
    def serialize_datetimes(self, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None
