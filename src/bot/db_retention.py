"""Фоновая уборка «старых» строк БД по политике части 2 плана очистки (ретеншн).

Джобы регистрируются в AsyncIOScheduler бота (`run_db_retention_pass`).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

import utils

logger = logging.getLogger("redmine_bot")

JOB_DB_RETENTION = "job_db_retention"


def retention_jobs_enabled() -> bool:
    v = os.getenv("DB_RETENTION_JOBS_ENABLED", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def retention_days_default() -> int:
    raw = os.getenv("DB_RETENTION_DAYS", "30").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 30


def retention_batch_size() -> int:
    raw = os.getenv("DB_RETENTION_BATCH_SIZE", "500").strip()
    try:
        n = int(raw)
    except ValueError:
        return 500
    return max(10, min(10_000, n))


def dlq_warn_row_threshold() -> int | None:
    """Если строк в DLQ больше порога — логируем WARNING. 0 / off — без проверки."""
    raw = (os.getenv("DB_DLQ_WARN_ROWS") or "5000").strip().lower()
    if raw in ("0", "", "off", "false", "no"):
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return 5000


def _cutoff(days: int) -> datetime:
    """Горизонт ретеншна в таймзоне процесса бота (см. ``utils.BOT_TZ`` / cycle_settings)."""
    return datetime.now(utils.BOT_TZ) - timedelta(days=int(days))


async def _execute_delete_batch(session: AsyncSession, stmt: Any) -> int:
    res = await session.execute(stmt)
    return int(getattr(res, "rowcount", 0) or 0)


async def prune_pending_notifications_older_than(
    session: AsyncSession,
    *,
    cutoff: datetime,
    batch_size: int,
) -> int:
    from database.models import PendingNotification

    total = 0
    pk = PendingNotification.id
    while True:
        subq = (
            select(pk)
            .where(PendingNotification.created_at < cutoff)
            .order_by(pk.asc())
            .limit(batch_size)
        )
        stmt = delete(PendingNotification).where(pk.in_(subq))
        n = await _execute_delete_batch(session, stmt)
        total += n
        await session.commit()
        if n < batch_size:
            break
    return total


async def prune_bot_ops_audit_older_than(
    session: AsyncSession,
    *,
    cutoff: datetime,
    batch_size: int,
) -> int:
    from database.models import BotOpsAudit

    total = 0
    pk = BotOpsAudit.id
    while True:
        subq = (
            select(pk).where(BotOpsAudit.created_at < cutoff).order_by(pk.asc()).limit(batch_size)
        )
        stmt = delete(BotOpsAudit).where(pk.in_(subq))
        n = await _execute_delete_batch(session, stmt)
        total += n
        await session.commit()
        if n < batch_size:
            break
    return total


async def prune_expired_bot_sessions(
    session: AsyncSession,
    *,
    now_ts: datetime,
    batch_size: int,
) -> int:
    from database.models import BotSession

    total = 0
    pk = BotSession.session_token
    while True:
        subq = (
            select(pk)
            .where(BotSession.expires_at < now_ts)
            .order_by(BotSession.created_at.asc())
            .limit(batch_size)
        )
        stmt = delete(BotSession).where(pk.in_(subq))
        n = await _execute_delete_batch(session, stmt)
        total += n
        await session.commit()
        if n < batch_size:
            break
    return total


async def prune_magic_tokens(
    session: AsyncSession,
    *,
    now_ts: datetime,
    created_before: datetime,
    batch_size: int,
) -> int:
    """Истёкшие коды по времени; used-строки старее created_before удаляются батчами."""
    from database.models import BotMagicToken

    pk = BotMagicToken.id

    async def sweep(where_clause: Any, order_cols: tuple[Any, ...]) -> int:
        local_total = 0
        while True:
            subq = select(pk).where(where_clause).order_by(*order_cols).limit(batch_size)
            stmt = delete(BotMagicToken).where(pk.in_(subq))
            n = await _execute_delete_batch(session, stmt)
            local_total += n
            await session.commit()
            if n < batch_size:
                break
        return local_total

    n_expired = await sweep(
        BotMagicToken.expires_at < now_ts,
        (BotMagicToken.created_at.asc(),),
    )
    n_used = await sweep(
        (BotMagicToken.used_at.isnot(None)) & (BotMagicToken.created_at < created_before),
        (BotMagicToken.created_at.asc(),),
    )
    return n_expired + n_used


async def prune_password_reset_tokens(
    session: AsyncSession,
    *,
    now_ts: datetime,
    created_before: datetime,
    batch_size: int,
) -> int:
    from database.models import PasswordResetToken

    pk = PasswordResetToken.id

    async def sweep(where_clause: Any, order_cols: tuple[Any, ...]) -> int:
        local_total = 0
        while True:
            subq = select(pk).where(where_clause).order_by(*order_cols).limit(batch_size)
            stmt = delete(PasswordResetToken).where(pk.in_(subq))
            n = await _execute_delete_batch(session, stmt)
            local_total += n
            await session.commit()
            if n < batch_size:
                break
        return local_total

    n_expired = await sweep(
        PasswordResetToken.expires_at < now_ts,
        (PasswordResetToken.created_at.asc(),),
    )
    n_used = await sweep(
        (PasswordResetToken.used_at.isnot(None)) & (PasswordResetToken.created_at < created_before),
        (PasswordResetToken.created_at.asc(),),
    )
    return n_expired + n_used


async def prune_matrix_room_bindings(
    session: AsyncSession,
    *,
    now_ts: datetime,
    created_before: datetime,
    batch_size: int,
) -> int:
    from database.models import MatrixRoomBinding

    pk = MatrixRoomBinding.id

    async def sweep(where_clause: Any, order_cols: tuple[Any, ...]) -> int:
        local_total = 0
        while True:
            subq = select(pk).where(where_clause).order_by(*order_cols).limit(batch_size)
            stmt = delete(MatrixRoomBinding).where(pk.in_(subq))
            n = await _execute_delete_batch(session, stmt)
            local_total += n
            await session.commit()
            if n < batch_size:
                break
        return local_total

    n_expired = await sweep(
        MatrixRoomBinding.expires_at < now_ts,
        (MatrixRoomBinding.created_at.asc(),),
    )
    n_used = await sweep(
        (MatrixRoomBinding.used_at.isnot(None)) & (MatrixRoomBinding.created_at < created_before),
        (MatrixRoomBinding.created_at.asc(),),
    )
    return n_expired + n_used


async def prune_bot_watcher_cache_stale(
    session: AsyncSession,
    *,
    cutoff: datetime,
    batch_size: int,
) -> int:
    """Старые строки кэша наблюдателей по ``updated_at`` (orphan / давно не тикаемые задачи)."""
    from database.models import BotWatcherCache

    total = 0
    while True:
        subq = (
            select(BotWatcherCache.user_id, BotWatcherCache.issue_id)
            .where(BotWatcherCache.updated_at < cutoff)
            .order_by(BotWatcherCache.updated_at.asc())
            .limit(batch_size)
        )
        stmt = delete(BotWatcherCache).where(
            tuple_(BotWatcherCache.user_id, BotWatcherCache.issue_id).in_(subq)
        )
        n = await _execute_delete_batch(session, stmt)
        total += n
        await session.commit()
        if n < batch_size:
            break
    return total


async def prune_bot_issue_dedup_older_than(
    session: AsyncSession,
    *,
    cutoff: datetime,
    batch_size: int,
) -> int:
    """Ретеншн dedup-state: строки без активных событий старше горизонта по ``updated_at``."""
    from database.models import BotIssueDedupState

    total = 0
    pk = BotIssueDedupState.id
    while True:
        subq = (
            select(pk)
            .where(BotIssueDedupState.updated_at < cutoff)
            .order_by(pk.asc())
            .limit(batch_size)
        )
        stmt = delete(BotIssueDedupState).where(pk.in_(subq))
        n = await _execute_delete_batch(session, stmt)
        total += n
        await session.commit()
        if n < batch_size:
            break
    return total


async def pending_notifications_count(session: AsyncSession) -> int:
    from database.models import PendingNotification

    res = await session.execute(select(func.count()).select_from(PendingNotification))
    return int(res.scalar_one())


async def run_db_retention_pass() -> None:
    """Один цикл очистки: вызывать из планировщика (ночью)."""
    if not retention_jobs_enabled():
        logger.debug("db_retention: disabled (DB_RETENTION_JOBS_ENABLED=0)")
        return

    try:
        await _run_db_retention_pass_inner()
    except Exception:
        logger.exception("db_retention: pass failed")


async def _run_db_retention_pass_inner() -> None:
    from database.session import get_session_factory

    days = retention_days_default()
    batch = retention_batch_size()
    cutoff = _cutoff(days)
    now_ts = datetime.now(utils.BOT_TZ)

    factory = get_session_factory()
    logger.info(
        "db_retention: start days=%s batch=%s cutoff=%s now=%s",
        days,
        batch,
        cutoff.isoformat(),
        now_ts.isoformat(),
    )

    totals: dict[str, int] = {}
    dlq_remaining: int | None = None

    async with factory() as session:
        totals["pending_notifications"] = await prune_pending_notifications_older_than(
            session, cutoff=cutoff, batch_size=batch
        )
        totals["bot_ops_audit"] = await prune_bot_ops_audit_older_than(
            session, cutoff=cutoff, batch_size=batch
        )

        totals["bot_sessions_expired"] = await prune_expired_bot_sessions(
            session, now_ts=now_ts, batch_size=batch
        )
        totals["bot_magic_tokens"] = await prune_magic_tokens(
            session,
            now_ts=now_ts,
            created_before=cutoff,
            batch_size=batch,
        )
        totals["password_reset_tokens"] = await prune_password_reset_tokens(
            session,
            now_ts=now_ts,
            created_before=cutoff,
            batch_size=batch,
        )
        totals["matrix_room_bindings"] = await prune_matrix_room_bindings(
            session,
            now_ts=now_ts,
            created_before=cutoff,
            batch_size=batch,
        )
        totals["bot_watcher_cache_stale"] = await prune_bot_watcher_cache_stale(
            session, cutoff=cutoff, batch_size=batch
        )
        totals["bot_issue_dedup_state"] = await prune_bot_issue_dedup_older_than(
            session, cutoff=cutoff, batch_size=batch
        )

        dlq_remaining = await pending_notifications_count(session)
        thresh = dlq_warn_row_threshold()
        if thresh is not None and dlq_remaining > thresh:
            logger.warning(
                "db_retention: pending_notifications rows=%s exceed DB_DLQ_WARN_ROWS=%s",
                dlq_remaining,
                thresh,
            )

    logger.info(
        "db_retention: done totals=%s pending_notifications_remaining=%s",
        totals,
        dlq_remaining,
    )
