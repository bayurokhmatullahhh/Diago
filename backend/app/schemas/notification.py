from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_serializer


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    todo_id: int | None
    todo_title: str
    scheduled_at: datetime
    delivered_at: datetime
    is_read: bool

    @field_serializer("scheduled_at", "delivered_at")
    def serialize_datetimes(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
