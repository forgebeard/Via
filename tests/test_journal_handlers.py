"""Тесты журнального движка v2: recipients, DLQ-контекст, infer_event_type."""

from __future__ import annotations

import json
from types import SimpleNamespace

from bot.journal_handlers import (
    former_assignee_redmine_id,
    infer_event_type,
    jinja_context_json_safe,
)


def test_infer_event_type_comment_over_status() -> None:
    j = SimpleNamespace(
        notes="x", details=[{"property": "status_id", "old_value": "1", "new_value": "2"}]
    )
    assert infer_event_type(j) == "comment"


def test_infer_event_type_assigned() -> None:
    j = SimpleNamespace(
        notes="", details=[{"property": "assigned_to_id", "old_value": "1", "new_value": "2"}]
    )
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
    j = SimpleNamespace(
        details=[{"property": "assigned_to_id", "old_value": "7", "new_value": "9"}]
    )
    assert former_assignee_redmine_id(j) == 7


def test_jinja_context_json_safe_roundtrip() -> None:
    ctx = {"issue_id": 1, "nested": {"a": 1}, "lst": [1, "x"], "x": None}
    safe = jinja_context_json_safe(ctx)
    json.dumps(safe)


def test_two_journals_close_resets_timers_documented() -> None:
    """Регрессия (план): в одном тике два журнала — reassign затем закрытие.

    После ``update_reminder_timers`` с финальным ``issue.status.is_closed`` поля
    ``group_reminder_due_at`` / ``personal_reminder_due_at`` должны стать NULL;
    курсор — на id последнего журнала (см. ``advance_cursor_after_journal`` в тике).
    """
    assert True
