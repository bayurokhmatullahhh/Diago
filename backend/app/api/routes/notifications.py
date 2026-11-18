from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse, summary="List delivered reminders")
def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    items = list(
        db.scalars(
            select(Notification)
            .order_by(Notification.delivered_at.desc(), Notification.id.desc())
            .limit(limit)
        ).all()
    )
    unread_count = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.is_read.is_(False))
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread_count or 0,
    )


@router.patch("/read-all", summary="Mark all notifications as read")
def mark_all_read(db: Session = Depends(get_db)) -> dict[str, int]:
    result = db.execute(
        update(Notification)
        .where(Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"updated": result.rowcount or 0}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int, db: Session = Depends(get_db)
) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification
