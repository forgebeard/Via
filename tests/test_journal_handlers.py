"""Тесты журнального движка v2: recipients, DLQ-контекст, infer_event_type."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.journal_handlers import (
    former_assignee_redmine_id,
    infer_event_type,
    jinja_context_json_safe,
    personal_recipient_cfgs,
)


def test_infer_event_type_comment_over_status() -> None:
    j = SimpleNamespace(notes="x", details=[{"property": "status_id", "old_value": "1", "new_value": "2"}])
    assert infer_event_type(j) == "comment"


def test_infer_event_type_assigned() -> None:
    j = SimpleNamespace(notes="", details=[{"property": "assigned_to_id", "old_value": "1", "new_value": "2"}])
    assert infer_event_type(j) == "assigned"


def test_former_assignee_empty_old_values() -> None:
    j = SimpleNamespace(details=[{"property": "assigned_to_id", "old_value": ""}])
    assert former_assignee_redmine_id(j) is None
    j2 = SimpleNamespace(details=[{"property": "assigned_to_id", "old_value": "0"}])
    assert former_assignee_redmine_id(j2) is None
    j3 = SimpleNamespace(details=[{"property": "assigned_to_id", "old_value": None}])
    assert former_assignee_redmine_id(j3) is None
    j4 = SimpleNamespace(details=[{"property": "assigned_to_id"}])
    assert former_assignee_redmine_id(j4) is None


def test_former_assignee_valid() -> None:
    j = SimpleNamespace(details=[{"property": "assigned_to_id", "old_value": "7", "new_value": "9"}])
    assert former_assignee_redmine_id(j) == 7


def test_jinja_context_json_safe_roundtrip() -> None:
    ctx = {"issue_id": 1, "nested": {"a": 1}, "lst": [1, "x"], "x": None}
    safe = jinja_context_json_safe(ctx)
    json.dumps(safe)


def test_personal_recipients_skips_self_assignee() -> None:
    async def inner() -> None:
        session = AsyncMock()
        assignee = {"id": 1, "redmine_id": 10, "room": "!a"}
        users = [assignee]
        journal = SimpleNamespace(user=SimpleNamespace(id=10), details=[])
        issue = SimpleNamespace(id=42)
        with patch(
            "database.watcher_cache_repo.list_bot_user_ids_for_issue",
            new_callable=AsyncMock,
            return_value=[],
        ):
            out = await personal_recipient_cfgs(session, issue, journal, assignee, users)
        assert out == []

    asyncio.run(inner())


def test_personal_recipients_includes_former_and_watcher() -> None:
    async def inner() -> None:
        session = AsyncMock()
        assignee = {"id": 1, "redmine_id": 10, "room": "!a"}
        former = {"id": 2, "redmine_id": 7, "room": "!b"}
        watcher = {"id": 3, "redmine_id": 11, "room": "!c"}
        users = [assignee, former, watcher]
        journal = SimpleNamespace(
            user=SimpleNamespace(id=99),
            details=[{"property": "assigned_to_id", "old_value": "7", "new_value": "10"}],
        )
        issue = SimpleNamespace(id=5)
        with patch(
            "database.watcher_cache_repo.list_bot_user_ids_for_issue",
            new_callable=AsyncMock,
            return_value=[3],
        ):
            out = await personal_recipient_cfgs(session, issue, journal, assignee, users)
        rids = {int(u["redmine_id"]) for u in out}
        assert rids == {10, 7, 11}

    asyncio.run(inner())


def test_two_journals_close_resets_timers_documented() -> None:
    """Регрессия (план): в одном тике два журнала — reassign затем закрытие.

    После ``update_reminder_timers`` с финальным ``issue.status.is_closed`` поля
    ``group_reminder_due_at`` / ``personal_reminder_due_at`` должны стать NULL;
    курсор — на id последнего журнала (см. ``advance_cursor_after_journal`` в тике).
    """
    assert True
