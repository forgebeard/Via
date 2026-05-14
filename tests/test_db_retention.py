"""Тесты настроек и одного запуска `run_db_retention_pass` с моком сессии."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_retention_helpers_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("DB_RETENTION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("DB_RETENTION_JOBS_ENABLED", raising=False)
    monkeypatch.delenv("DB_DLQ_WARN_ROWS", raising=False)

    import bot.db_retention as dr

    assert dr.retention_jobs_enabled() is True
    assert dr.retention_days_default() == 30
    assert dr.retention_batch_size() == 500
    assert dr.dlq_warn_row_threshold() == 5000


def test_cutoff_uses_bot_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    from zoneinfo import ZoneInfo

    import utils as utils_mod

    tz = ZoneInfo("Asia/Yekaterinburg")
    monkeypatch.setattr(utils_mod, "BOT_TZ", tz)

    import bot.db_retention as dr

    c = dr._cutoff(7)
    assert c.tzinfo is not None
    assert c.tzinfo == tz


@pytest.mark.parametrize(
    ("env_warn", "expected"),
    [("off", None), ("0", None)],
)
def test_dlq_warn_disabled(
    monkeypatch: pytest.MonkeyPatch, env_warn: str, expected: int | None
) -> None:
    monkeypatch.setenv("DB_DLQ_WARN_ROWS", env_warn)

    import bot.db_retention as dr

    assert dr.dlq_warn_row_threshold() is expected


@pytest.mark.asyncio
async def test_run_db_retention_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import database.session as ds

    monkeypatch.setenv("DB_RETENTION_JOBS_ENABLED", "0")
    spy = AsyncMock(side_effect=RuntimeError("should not DB"))
    monkeypatch.setattr(ds, "get_session_factory", spy)

    import bot.db_retention as dr

    await dr.run_db_retention_pass()
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_run_db_retention_one_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    import database.session as ds

    monkeypatch.delenv("DB_RETENTION_JOBS_ENABLED", raising=False)

    session = AsyncMock(name="sess")
    count_res = MagicMock()
    count_res.scalar_one = MagicMock(return_value=41)
    session.execute = AsyncMock(return_value=count_res)

    sess_factory = MagicMock()
    sess_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    sess_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(ds, "get_session_factory", lambda: sess_factory)

    import bot.db_retention as dr

    async def _zero(*_: object, **__: object) -> int:
        return 0

    monkeypatch.setattr(dr, "prune_pending_notifications_older_than", _zero)
    monkeypatch.setattr(dr, "prune_bot_ops_audit_older_than", _zero)
    monkeypatch.setattr(dr, "prune_expired_bot_sessions", _zero)
    monkeypatch.setattr(dr, "prune_magic_tokens", _zero)
    monkeypatch.setattr(dr, "prune_password_reset_tokens", _zero)
    monkeypatch.setattr(dr, "prune_matrix_room_bindings", _zero)
    monkeypatch.setattr(dr, "prune_bot_watcher_cache_stale", _zero)
    monkeypatch.setattr(dr, "prune_bot_issue_dedup_older_than", _zero)

    await dr.run_db_retention_pass()

    session.execute.assert_awaited_once()
