from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bot.sender as sender_mod
from bot.journal_handlers import build_journal_template_context, infer_event_type
from bot.journal_pipeline import aggregate_journals_first_old_last_new
from bot.template_context import build_issue_context, is_valid_http_issue_url
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
    j_reassigned = MockJournal(
        details=[{"name": "assigned_to_id", "old_value": "10", "new_value": "20"}]
    )
    j_unassigned = MockJournal(
        details=[{"name": "assigned_to_id", "old_value": "10", "new_value": ""}]
    )
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


def test_reminder_elapsed_rendered_as_text() -> None:
    issue = MockIssue(issue_id=555)
    issue.updated_on = datetime.now(UTC) - timedelta(hours=2, minutes=30)
    ctx = build_issue_context(issue, catalogs=None, elapsed_human="2 ч 30 мин")
    assert "2 ч" in ctx["elapsed_human"]


def test_issue_url_falls_back_to_redmine_when_portal_empty(monkeypatch) -> None:
    issue = MockIssue(issue_id=321)
    monkeypatch.setattr(sender_mod, "PORTAL_BASE_URL", "")
    monkeypatch.setattr(sender_mod, "REDMINE_URL", "https://support.red-soft.ru")
    ctx = build_issue_context(issue, catalogs=None)
    assert ctx["issue_url"] == "https://support.red-soft.ru/issues/321"


def test_issue_url_reads_sender_values_dynamically(monkeypatch) -> None:
    issue = MockIssue(issue_id=322)
    monkeypatch.setattr(sender_mod, "PORTAL_BASE_URL", "")
    monkeypatch.setattr(sender_mod, "REDMINE_URL", "https://support.red-soft.ru")
    first_ctx = build_issue_context(issue, catalogs=None)
    assert first_ctx["issue_url"] == "https://support.red-soft.ru/issues/322"

    monkeypatch.setattr(sender_mod, "PORTAL_BASE_URL", "https://portal.red-soft.ru")
    second_ctx = build_issue_context(issue, catalogs=None)
    assert second_ctx["issue_url"] == "https://portal.red-soft.ru/issues/322"


def test_issue_url_empty_when_no_runtime_base(monkeypatch) -> None:
    issue = MockIssue(issue_id=323)
    monkeypatch.setattr(sender_mod, "PORTAL_BASE_URL", "")
    monkeypatch.setattr(sender_mod, "REDMINE_URL", "")

    import bot.main as main_mod

    monkeypatch.setattr(main_mod, "PORTAL_BASE_URL", "")
    monkeypatch.setattr(main_mod, "REDMINE_URL", "")

    monkeypatch.delenv("PORTAL_BASE_URL", raising=False)
    monkeypatch.delenv("REDMINE_URL", raising=False)

    ctx = build_issue_context(issue, catalogs=None)
    assert ctx["portal_base_url"] == ""
    assert ctx["issue_url"] == ""


def test_issue_url_falls_back_to_main_runtime_base(monkeypatch) -> None:
    issue = MockIssue(issue_id=324)
    monkeypatch.setattr(sender_mod, "PORTAL_BASE_URL", "")
    monkeypatch.setattr(sender_mod, "REDMINE_URL", "")

    import bot.main as main_mod

    monkeypatch.setattr(main_mod, "PORTAL_BASE_URL", "https://runtime.red-soft.ru")
    monkeypatch.setattr(main_mod, "REDMINE_URL", "")

    ctx = build_issue_context(issue, catalogs=None)
    assert ctx["portal_base_url"] == "https://runtime.red-soft.ru"
    assert ctx["issue_url"] == "https://runtime.red-soft.ru/issues/324"


def test_is_valid_http_issue_url_rejects_relative() -> None:
    assert is_valid_http_issue_url("https://support.red-soft.ru/issues/1")
    assert not is_valid_http_issue_url("/issues/1")
    assert not is_valid_http_issue_url("redv://redv/issues/1")
    assert not is_valid_http_issue_url("")


def test_aggregate_journals_first_old_last_new() -> None:
    j1 = MockJournal(
        journal_id=101,
        details=[{"name": "status_id", "old_value": "1", "new_value": "2"}],
    )
    j2 = MockJournal(
        journal_id=102,
        details=[
            {"name": "status_id", "old_value": "2", "new_value": "13"},
            {"name": "priority_id", "old_value": "2", "new_value": "3"},
        ],
    )
    agg = aggregate_journals_first_old_last_new([j1, j2])
    assert agg is not None
    assert agg.id == 102
    details = {d["name"]: d for d in agg.details}
    assert details["status_id"]["old_value"] == "1"
    assert details["status_id"]["new_value"] == "13"
