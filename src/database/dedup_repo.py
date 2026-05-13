"""Репозиторий дедупа журнальных уведомлений (new/issue_updated)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotIssueDedupState


def _axis_tuple(issue) -> tuple[int | None, int | None, int | None]:
    status_id = getattr(getattr(issue, "status", None), "id", None)
    version_obj = getattr(issue, "fixed_version", None) or getattr(issue, "target_version", None)
    version_id = getattr(version_obj, "id", None)
    priority_id = getattr(getattr(issue, "priority", None), "id", None)
    try:
        st = int(status_id) if status_id is not None else None
    except (TypeError, ValueError):
        st = None
    try:
        ver = int(version_id) if version_id is not None else None
    except (TypeError, ValueError):
        ver = None
    try:
        pr = int(priority_id) if priority_id is not None else None
    except (TypeError, ValueError):
        pr = None
    return st, ver, pr


async def should_send_journal_notification(
    session: AsyncSession,
    *,
    issue,
    room_id: str,
    notification_type: str,
) -> bool:
    """True если fingerprint осей изменился или записи нет."""
    room = (room_id or "").strip()
    if not room:
        return False
    issue_id = int(getattr(issue, "id", 0) or 0)
    if issue_id <= 0:
        return False
    status_id, version_id, priority_id = _axis_tuple(issue)
    row = await session.scalar(
        select(BotIssueDedupState).where(
            BotIssueDedupState.issue_id == issue_id,
            BotIssueDedupState.room_id == room,
            BotIssueDedupState.notification_type == notification_type,
        )
    )
    if row is None:
        return True
    return not (
        row.status_id == status_id
        and row.version_id == version_id
        and row.priority_id == priority_id
    )


async def mark_journal_notification_sent(
    session: AsyncSession,
    *,
    issue,
    room_id: str,
    notification_type: str,
) -> None:
    """Upsert состояния дедупа после успешной отправки."""
    room = (room_id or "").strip()
    issue_id = int(getattr(issue, "id", 0) or 0)
    if issue_id <= 0 or not room:
        return
    status_id, version_id, priority_id = _axis_tuple(issue)
    stmt = pg_insert(BotIssueDedupState).values(
        issue_id=issue_id,
        room_id=room,
        notification_type=notification_type,
        status_id=status_id,
        version_id=version_id,
        priority_id=priority_id,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_bot_issue_dedup_issue_room_type",
        set_={
            "status_id": stmt.excluded.status_id,
            "version_id": stmt.excluded.version_id,
            "priority_id": stmt.excluded.priority_id,
        },
    )
    await session.execute(stmt)
