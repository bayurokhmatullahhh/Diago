from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """A persisted in-app record of a reminder delivered by the worker."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("todo_id", "reminder_revision", name="uq_notification_todo_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    todo_id: Mapped[int | None] = mapped_column(
        ForeignKey("todos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    todo_title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reminder_revision: Mapped[int] = mapped_column(Integer)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
