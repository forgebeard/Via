"""Удаление state/DLQ/lease по Redmine user id — при удалении bot_users."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotIssueState, BotUserLease, PendingNotification


async def delete_runtime_data_for_redmine_user(session: AsyncSession, redmine_id: int) -> None:
    """Убирает строки, привязанные к user_redmine_id, до DELETE из bot_users."""
    await session.execute(delete(BotIssueState).where(BotIssueState.user_redmine_id == redmine_id))
    await session.execute(
        delete(PendingNotification).where(PendingNotification.user_redmine_id == redmine_id)
    )
    await session.execute(delete(BotUserLease).where(BotUserLease.user_redmine_id == redmine_id))
