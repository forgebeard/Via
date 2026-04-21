from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.digest_service import _aggregate_digest_items
from bot.journal_handlers import build_journal_template_context, infer_event_type
from bot.template_context import build_issue_context
from tests.conftest import MockIssue, MockJournal


def test_build_issue_context_contains_extended_fields() -> None:
    issue = MockIssue(issue_id=501, subject="Новая задача")
    issue.project = type("Project", (), {"name": "Infra"})()
    issue.assigned_to = type("Assignee", (), {"name": "Иван"})()
    issue.description = "Описание " * 80
    issue.due_date = "2026-04-30"
    ctx = build_issue_context(issue, catalogs=None)
    assert ctx["project_name"] == "Infra"
    assert ctx["assignee_name"] == "Иван"
    assert ctx["description_excerpt"]
    assert ctx["due_date"] == "2026-04-30"


def test_infer_event_type_reassigned_and_unassigned() -> None:
    j_reassigned = MockJournal(details=[{"name": "assigned_to_id", "old_value": "10", "new_value": "20"}])
    j_unassigned = MockJournal(details=[{"name": "assigned_to_id", "old_value": "10", "new_value": ""}])
    assert infer_event_type(j_reassigned) == "reassigned"
    assert infer_event_type(j_unassigned) == "unassigned"


def test_build_journal_template_context_contains_structured_changes() -> None:
    issue = MockIssue(issue_id=777, subject="Смена статуса")
    issue.status = type("Status", (), {"name": "В работе"})()
    issue.priority = type("Priority", (), {"name": "Нормальный"})()
    journal = MockJournal(
        notes="Проверил и обновил",
        details=[
            {"name": "status_id", "old_value": "1", "new_value": "2"},
            {"name": "priority_id", "old_value": "2", "new_value": "3"},
        ],
    )
    users = [{"id": 1, "redmine_id": 10, "full_name": "Бывший исполнитель"}]
    ctx = build_journal_template_context(
        issue=issue,
        journal=journal,
        catalogs=None,
        users=users,
        event_type="status_change",
        extra_text="Статус: Новая → В работе",
    )
    assert ctx["changes"]
    assert ctx["journal_notes"] == "Проверил и обновил"
    assert ctx["status_from"] in ("1", "Новая")


def test_aggregate_digest_items_keeps_comments_and_reminder_count() -> None:
    row1 = type(
        "Row",
        (),
        {
            "id": 1,
            "issue_id": 1001,
            "issue_subject": "Digest task",
            "event_type": "comment",
            "journal_notes": "Есть комментарий",
            "status_name": "В работе",
            "assigned_to": "Иван",
        },
    )()
    row2 = type(
        "Row",
        (),
        {
            "id": 2,
            "issue_id": 1001,
            "issue_subject": "Digest task",
            "event_type": "reminder",
            "journal_notes": "",
            "status_name": "В работе",
            "assigned_to": "Иван",
        },
    )()
    items = _aggregate_digest_items([row1, row2])
    assert len(items) == 1
    item = items[0]
    assert item["reminders_count"] == 1
    assert item["comments"] == ["Есть комментарий"]
    assert item["events"] == ["comment", "reminder"]


def test_reminder_elapsed_rendered_as_text() -> None:
    issue = MockIssue(issue_id=555)
    issue.updated_on = datetime.now(UTC) - timedelta(hours=2, minutes=30)
    ctx = build_issue_context(issue, catalogs=None, elapsed_human="2 ч 30 мин")
    assert "2 ч" in ctx["elapsed_human"]
