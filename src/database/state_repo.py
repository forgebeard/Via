"""
PostgreSQL storage для state бота и lease-координация между несколькими инстансами.

`bot_issue_state` хранит дедупликацию/таймеры уведомлений (sent/reminders/overdue/journals),
а `bot_user_leases` не даёт нескольким инстансам бота одновременно обрабатывать одного
пользователя в рамках одного цикла.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import or_

from database.models import BotIssueState, BotUserLease


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(dt: str) -> datetime:
    # ISO в коде сейчас — datetime.isoformat() с tz-aware из bot.py.
    return datetime.fromisoformat(dt)


def build_state_dicts_from_rows(rows: list[BotIssueState]) -> tuple[dict, dict, dict, dict]:
    """
    Преобразует строки `BotIssueState` в 4 словаря той же формы, что у JSON.
    """
    sent: dict[str, dict] = {}
    reminders: dict[str, dict] = {}
    overdue: dict[str, dict] = {}
    journals: dict[str, dict] = {}

    for r in rows:
        iid = str(r.issue_id)
        if r.last_status is not None and r.sent_notified_at is not None:
            sent[iid] = {"notified_at": _iso(r.sent_notified_at), "status": r.last_status}
        if r.last_reminder_at is not None:
            reminders[iid] = {"last_reminder": _iso(r.last_reminder_at)}
        if r.last_overdue_notified_at is not None:
            overdue[iid] = {"last_notified": _iso(r.last_overdue_notified_at)}
        if r.last_journal_id is not None:
            journals[iid] = {"last_journal_id": r.last_journal_id}

    return sent, reminders, overdue, journals


async def try_acquire_user_lease(
    session: AsyncSession,
    user_redmine_id: int,
    lease_owner_id: uuid.UUID,
    lease_until: datetime,
) -> bool:
    """
    Атомарно пытается захватить lease на пользователя.

    Возвращает True если lease получен этим инстансом.
    """
    stmt = pg_insert(BotUserLease).values(
        user_redmine_id=user_redmine_id,
        lease_owner_id=lease_owner_id,
        lease_until=lease_until,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[BotUserLease.user_redmine_id],
        set_={
            "lease_owner_id": lease_owner_id,
            "lease_until": lease_until,
        },
        where=or_(BotUserLease.lease_until < func.now(), BotUserLease.lease_owner_id == lease_owner_id),
    ).returning(BotUserLease.user_redmine_id)

    res = await session.execute(stmt)
    row = res.first()
    return row is not None


async def load_user_issue_state(
    session: AsyncSession,
    user_redmine_id: int,
) -> tuple[dict, dict, dict, dict]:
    """
    Загружает state для пользователя и возвращает (sent, reminders, overdue, journals).
    """
    res = await session.execute(
        select(BotIssueState).where(BotIssueState.user_redmine_id == user_redmine_id)
    )
    rows = list(res.scalars().all())
    return build_state_dicts_from_rows(rows)


def _fields_for_issue(
    iid: str,
    sent: dict,
    reminders: dict,
    overdue: dict,
    journals: dict,
) -> dict:
    """
    Собирает поля BotIssueState для одного issue_id из 4 dict-структур.
    """
    last_status = None
    sent_notified_at = None
    if iid in sent:
        last_status = sent[iid].get("status")
        sent_notified_at = _parse_iso(sent[iid].get("notified_at"))

    last_journal_id = None
    if iid in journals:
        last_journal_id = journals[iid].get("last_journal_id")

    last_reminder_at = None
    if iid in reminders:
        last_reminder_at = _parse_iso(reminders[iid].get("last_reminder"))

    last_overdue_notified_at = None
    if iid in overdue:
        last_overdue_notified_at = _parse_iso(overdue[iid].get("last_notified"))

    return {
        "last_status": last_status,
        "sent_notified_at": sent_notified_at,
        "last_journal_id": last_journal_id,
        "last_reminder_at": last_reminder_at,
        "last_overdue_notified_at": last_overdue_notified_at,
    }


async def upsert_user_issue_state(
    session: AsyncSession,
    user_redmine_id: int,
    issue_ids: Iterable[str],
    sent: dict,
    reminders: dict,
    overdue: dict,
    journals: dict,
) -> None:
    """
    Upsert изменённых issue state строк.

    `issue_ids` — набор issue_id строк, которые изменились в этом цикле.
    """
    ids = sorted({str(i) for i in issue_ids if i is not None})
    if not ids:
        return

    values = []
    for iid in ids:
        f = _fields_for_issue(iid, sent, reminders, overdue, journals)
        values.append(
            {
                "user_redmine_id": user_redmine_id,
                "issue_id": int(iid),
                **f,
            }
        )

    stmt = pg_insert(BotIssueState).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[BotIssueState.user_redmine_id, BotIssueState.issue_id],
        set_={
            "last_status": stmt.excluded.last_status,
            "sent_notified_at": stmt.excluded.sent_notified_at,
            "last_journal_id": stmt.excluded.last_journal_id,
            "last_reminder_at": stmt.excluded.last_reminder_at,
            "last_overdue_notified_at": stmt.excluded.last_overdue_notified_at,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


async def delete_state_rows_not_in_open(
    session: AsyncSession,
    user_redmine_id: int,
    open_issue_ids: set[str],
) -> int:
    """
    Удаляет state строки для закрытых issue (аналог cleanup_state_files для JSON).
    """
    if not open_issue_ids:
        # Если вдруг open пуст — удаляем всё для пользователя
        res = await session.execute(
            delete(BotIssueState).where(BotIssueState.user_redmine_id == user_redmine_id)
        )
        return getattr(res, "rowcount", 0) or 0

    ids_int = [int(i) for i in open_issue_ids]
    # NOT IN (..) может быть длинным, но для MVP повторяет текущую логику cleanup по JSON.
    res = await session.execute(
        delete(BotIssueState).where(
            BotIssueState.user_redmine_id == user_redmine_id,
            ~BotIssueState.issue_id.in_(ids_int),
        )
    )
    return getattr(res, "rowcount", 0) or 0

