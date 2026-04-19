"""Фазы A/B: глобальный поллинг задач и выборка журналов по курсору."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from bot.async_utils import run_in_thread
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.journal_cursor_repo import get_last_journal_id, upsert_last_journal_id
from database.models import BotUser, CycleSettings
from database.watcher_cache_repo import replace_watchers_for_issue

logger = logging.getLogger("redmine_bot")


def _redmine_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _cycle_str(session: AsyncSession, key: str, default: str = "") -> str:
    row = await session.scalar(select(CycleSettings.value).where(CycleSettings.key == key))
    return (str(row).strip() if row is not None else default)


async def _set_cycle_str(session: AsyncSession, key: str, value: str) -> None:
    await session.execute(update(CycleSettings).where(CycleSettings.key == key).values(value=value))


def _parse_watermark(raw: str) -> datetime:
    s = (raw or "").strip()
    if not s:
        return datetime(1970, 1, 1, tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=UTC)


def _max_updated_on(issues: list[Any]) -> datetime | None:
    best: datetime | None = None
    for iss in issues:
        uo = getattr(iss, "updated_on", None)
        if uo is None:
            continue
        try:
            dt = uo
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if getattr(dt, "tzinfo", None) is None:
                dt = dt.replace(tzinfo=UTC)
            dt = dt.astimezone(UTC)
            if best is None or dt > best:
                best = dt
        except Exception:
            continue
    return best


async def phase_a_candidates(
    redmine: Any,
    session: AsyncSession,
    *,
    bot_user_redmine_ids: set[int],
    watched_issue_ids: set[int],
    max_issues: int,
    max_pages: int,
) -> tuple[list[Any], datetime | None]:
    """
    Один проход по Redmine ``updated_on >= LAST_ISSUES_POLL_AT`` без assigned_to/status_id.

    Возвращает (кандидаты в scope, max_updated_on по **всем** строкам ответа для водяного знака).
    """
    wm_raw = await _cycle_str(session, "LAST_ISSUES_POLL_AT", "")
    wm = _parse_watermark(wm_raw)
    ts = _redmine_ts(wm)

    collected: list[Any] = []
    max_on: datetime | None = None
    offset = 0
    for _page in range(max(1, max_pages)):
        params: dict[str, Any] = {
            "updated_on": f">={ts}",
            "sort": "updated_on:asc",
            "limit": max_issues,
            "offset": offset,
        }
        try:
            batch = await run_in_thread(lambda p=params: list(redmine.issue.filter(**p)))
        except Exception as e:
            logger.error("journal_phase_a_redmine_failed: %s", e, exc_info=True)
            break
        if not batch:
            break
        mo = _max_updated_on(batch)
        if mo is not None and (max_on is None or mo > max_on):
            max_on = mo
        collected.extend(batch)
        if len(batch) < max_issues:
            break
        offset += len(batch)

    in_scope: list[Any] = []
    for iss in collected:
        try:
            aid = getattr(getattr(iss, "assigned_to", None), "id", None)
        except Exception:
            aid = None
        iid = int(getattr(iss, "id", 0) or 0)
        if aid is not None and int(aid) in bot_user_redmine_ids:
            in_scope.append(iss)
            continue
        if iid and iid in watched_issue_ids:
            in_scope.append(iss)
    return in_scope, max_on


async def persist_watermark(session: AsyncSession, max_on: datetime | None) -> None:
    if max_on is None:
        return
    await _set_cycle_str(session, "LAST_ISSUES_POLL_AT", max_on.astimezone(UTC).isoformat())


async def load_bot_user_redmine_ids(session: AsyncSession) -> set[int]:
    r = await session.execute(select(BotUser.redmine_id))
    return {int(x[0]) for x in r.all()}


async def reload_issue_with_journals(redmine: Any, issue_id: int) -> Any:
    return await run_in_thread(
        lambda: redmine.issue.get(issue_id, include=["journals", "watchers"])
    )


async def sync_watcher_cache_for_issue(
    session: AsyncSession,
    issue: Any,
    *,
    redmine_id_to_bot_id: dict[int, int],
) -> None:
    ids: list[int] = []
    try:
        for w in getattr(issue, "watchers", None) or []:
            rid = getattr(w, "id", None)
            if rid is None:
                continue
            bid = redmine_id_to_bot_id.get(int(rid))
            if bid is not None:
                ids.append(bid)
    except Exception:
        pass
    await replace_watchers_for_issue(session, int(issue.id), ids)


async def iter_new_journals_for_issue(
    session: AsyncSession,
    issue: Any,
) -> list[Any]:
    last = await get_last_journal_id(session, int(issue.id))
    try:
        all_j = sorted(list(issue.journals or []), key=lambda j: int(j.id))
    except Exception:
        return []
    return [j for j in all_j if int(j.id) > int(last)]


async def advance_cursor_after_journal(
    session: AsyncSession,
    issue_id: int,
    journal_id: int,
) -> None:
    await upsert_last_journal_id(session, issue_id, journal_id)
