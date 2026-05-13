"""Планировщик: периодические задачи бота."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nio import AsyncClient
    from redminelib import Redmine

logger = logging.getLogger("redmine_bot")


def _cycle_slow_threshold_sec() -> float:
    raw = (os.getenv("BOT_CYCLE_SLOW_SEC") or "").strip()
    if not raw:
        return 30.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 30.0


async def check_all_users(
    client: AsyncClient,
    redmine: Redmine,
    *,
    now_tz: Callable[[], datetime],
    check_interval: int,
    runtime_status_file: Path,
    bot_instance_id,
    bot_lease_ttl: int,
    redmine_client_for_user: Callable[[Redmine, dict[str, Any]], Redmine],
    last_check_time: dict[int, datetime],
    max_concurrent: int = 5,
) -> None:
    """Проверка задач ВСЕХ пользователей. Параллельно по max_concurrent."""

    from bot import config_state as _cs
    from bot.catalogs import load_catalogs
    from bot.config_hot_reload import refresh_runtime_lists_from_db
    from bot.journal_tick import run_journal_tick
    from bot.sender import reset_dm_failed
    from database.session import get_session_factory

    start = time.monotonic()
    reset_dm_failed()
    logger.debug("🔍 Проверка в %s...", now_tz().strftime("%H:%M:%S"))

    session_factory = get_session_factory()
    await refresh_runtime_lists_from_db(session_factory)
    catalogs = None
    try:
        async with session_factory() as session:
            catalogs = await load_catalogs(session)
            _cs.CATALOGS = catalogs
    except Exception as e:
        logger.warning("⚠ catalogs_refresh_failed: %s", e)

    try:
        await run_journal_tick(client, redmine, now_tz=now_tz, catalogs=catalogs)
    except Exception as e:
        logger.error("❌ journal_tick: %s", e, exc_info=True)
    elapsed = time.monotonic() - start
    try:
        runtime_status_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_cycle_at": now_tz().isoformat(),
            "last_cycle_duration_s": round(elapsed, 3),
            "error_count": 0,
            "journal_engine": "v5_only",
        }
        runtime_status_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug("Не удалось обновить runtime_status.json", exc_info=True)
    threshold = _cycle_slow_threshold_sec()
    if elapsed > threshold:
        logger.info("✅ Журнальный цикл завершён за %.1fс (slow>%ss)", elapsed, threshold)
    else:
        logger.debug("✅ Журнальный цикл завершён за %.1fс", elapsed)
    return


async def cleanup_state_files(
    redmine: Redmine,
    *,
    now_tz: Callable[[], datetime],
    redmine_client_for_user: Callable[[Redmine, dict[str, Any]], Redmine],
) -> None:
    """Очистка state в Postgres для закрытых задач (03:00)."""
    from bot.config_hot_reload import refresh_runtime_lists_from_db
    from bot.config_state import USERS
    from database.session import get_session_factory
    from database.state_repo import delete_state_rows_not_in_open

    session_factory = get_session_factory()
    await refresh_runtime_lists_from_db(session_factory)

    logger.info("🧹 Очистка state в Postgres для закрытых задач (03:00)...")

    async with session_factory() as session:
        for user_cfg in USERS:
            uid = user_cfg["redmine_id"]
            rm_user = redmine_client_for_user(redmine, user_cfg)
            try:
                open_issues = list(rm_user.issue.filter(assigned_to_id=uid, status_id="open"))
            except Exception as e:
                logger.error(
                    "❌ Redmine (%s, user %s): %s", "очистка state (db)", uid, e, exc_info=True
                )
                continue

            open_ids = {str(i.id) for i in open_issues}
            try:
                await delete_state_rows_not_in_open(session, uid, open_ids)
            except Exception as e:
                logger.error("❌ DB cleanup user %s: %s", uid, e, exc_info=True)

        await session.commit()

    logger.info("🧹 Очистка state в Postgres завершена")


async def retry_dlq_notifications(
    client: AsyncClient,
    *,
    now_tz: Callable[[], datetime],
    batch_limit: int | None = None,
) -> int:
    """Повторная отправка уведомлений из dead-letter queue.

    Записи журнала с ``payload.needs_rerender`` снова рендерятся из шаблона в БД,
    затем отправляется готовое Matrix-тело. Остальные записи — как раньше
    (payload уже ``m.room.message``).

    Возвращает количество успешно доставленных уведомлений.
    """
    from bot.sender import resolve_room
    from bot.template_loader import render_named_template
    from database.dlq_repo import (
        MAX_DLQ_RETRIES,
        dequeue_due_notifications,
        mark_failed,
        mark_sent,
    )
    from database.session import get_session_factory
    from matrix_send import room_send_with_retry

    session_factory = get_session_factory()
    processed = 0

    async with session_factory() as session:
        due = await dequeue_due_notifications(session, limit=batch_limit)
        if not due:
            return 0

        logger.info("🔄 DLQ retry: %d уведомлений готово к отправке", len(due))

        for notif in due:
            try:
                p = notif.payload if isinstance(notif.payload, dict) else {}
                if p.get("needs_rerender"):
                    tpl = str(p.get("template_name") or "tpl_task_change")
                    ctx = p.get("jinja_context") if isinstance(p.get("jinja_context"), dict) else {}
                    plain = str(p.get("plain_body") or f"#{notif.issue_id}")
                    html, plain_tpl = await render_named_template(session, tpl, ctx)
                    matrix_plain = plain_tpl if plain_tpl is not None else plain
                    content = {
                        "msgtype": "m.text",
                        "body": matrix_plain,
                        "format": "org.matrix.custom.html",
                        "formatted_body": html,
                    }
                else:
                    content = notif.payload
                resolved = await resolve_room(client, notif.room_id)
                await room_send_with_retry(client, resolved, content, txn_id=f"dlq_{int(notif.id)}")
                await mark_sent(session, notif.id)
                processed += 1
                logger.info(
                    "✅ DLQ retry #%s → %s (попытка %d/%d)",
                    notif.issue_id,
                    notif.room_id[:20],
                    notif.retry_count,
                    MAX_DLQ_RETRIES,
                )
            except Exception as e:
                await mark_failed(session, notif.id, str(e))
                logger.warning(
                    "⚠ DLQ retry #%s failed (попытка %d/%d): %s",
                    notif.issue_id,
                    notif.retry_count + 1,
                    MAX_DLQ_RETRIES,
                    e,
                )

        await session.commit()

    logger.info("✅ DLQ retry завершена: %d/%d успешно", processed, len(due))
    return processed
