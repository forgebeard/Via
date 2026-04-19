"""Dead-letter queue для уведомлений, не доставленных в Matrix.

При сбое отправки уведомление сохраняется в pending_notifications
и повторяется при следующем цикле retry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PendingNotification

MAX_DLQ_RETRIES = 5
DLQ_RETRY_DELAY_SEC = 120  # 2 минуты


async def enqueue_notification(
    session: AsyncSession,
    user_redmine_id: int,
    issue_id: int,
    room_id: str,
    notification_type: str,
    payload: dict,
    error: str,
) -> None:
    """Сохраняет неудачное уведомление в DLQ."""
    now = datetime.now(UTC)
    stmt = pg_insert(PendingNotification).values(
        user_redmine_id=user_redmine_id,
        issue_id=issue_id,
        room_id=room_id,
        notification_type=notification_type,
        payload=payload,
        retry_count=0,
        last_error=error,
        next_retry_at=now + timedelta(seconds=DLQ_RETRY_DELAY_SEC),
    )
    await session.execute(stmt)


async def dequeue_due_notifications(
    session: AsyncSession,
    now: datetime | None = None,
    *,
    limit: int | None = None,
) -> list[PendingNotification]:
    """Возвращает уведомления, готовые к повторной отправке."""
    now = now or datetime.now(UTC)
    stmt = (
        select(PendingNotification)
        .where(
            PendingNotification.next_retry_at.isnot(None),
            PendingNotification.next_retry_at <= now,
            PendingNotification.retry_count < MAX_DLQ_RETRIES,
        )
        .order_by(PendingNotification.created_at)
    )
    if limit is not None and limit > 0:
        stmt = stmt.limit(int(limit))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_sent(session: AsyncSession, notification_id: int) -> None:
    """Удаляет уведомление из DLQ после успешной отправки."""
    from sqlalchemy import delete

    stmt = delete(PendingNotification).where(PendingNotification.id == notification_id)
    await session.execute(stmt)


async def mark_failed(
    session: AsyncSession,
    notification_id: int,
    error: str,
) -> PendingNotification | None:
    """Увеличивает retry_count и откладывает следующую попытку."""
    result = await session.execute(
        select(PendingNotification).where(PendingNotification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return None

    notification.retry_count += 1
    notification.last_error = error
    notification.next_retry_at = datetime.now(UTC) + timedelta(
        seconds=DLQ_RETRY_DELAY_SEC * (2 ** (notification.retry_count - 1))
    )
    return notification
