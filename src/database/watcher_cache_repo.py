"""Кэш наблюдателей: ``bot_watcher_cache``."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotWatcherCache


async def replace_watchers_for_issue(
    session: AsyncSession,
    issue_id: int,
    user_ids: list[int],
) -> None:
    """Полная замена строк для ``issue_id`` на переданный список ``bot_users.id``."""
    await session.execute(delete(BotWatcherCache).where(BotWatcherCache.issue_id == issue_id))
    now = datetime.now(UTC)
    for uid in user_ids:
        stmt = pg_insert(BotWatcherCache).values(
            user_id=int(uid),
            issue_id=int(issue_id),
            updated_at=now,
        )
        await session.execute(stmt)


async def issue_ids_watched_by_bot_users(session: AsyncSession) -> set[int]:
    r = await session.execute(select(BotWatcherCache.issue_id).distinct())
    return {int(x[0]) for x in r.all()}


async def list_bot_user_ids_for_issue(session: AsyncSession, issue_id: int) -> list[int]:
    """Список ``bot_users.id`` из кэша наблюдателей для задачи."""
    r = await session.execute(
        select(BotWatcherCache.user_id).where(BotWatcherCache.issue_id == int(issue_id))
    )
    return [int(x[0]) for x in r.all()]


async def delete_stale_watcher_rows(
    session: AsyncSession,
    issue_ids: list[int],
    *,
    updated_before: datetime,
) -> None:
    """Удаляет записи по issue_id, не обновлённые после ``updated_before`` (refresh N тиков)."""
    if not issue_ids:
        return
    await session.execute(
        delete(BotWatcherCache).where(
            BotWatcherCache.issue_id.in_(issue_ids),
            BotWatcherCache.updated_at < updated_before,
        )
    )
