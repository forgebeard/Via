"""Единый Jinja-контекст для issue-шаблонов (tpl_new_issue, tpl_task_change, tpl_reminder)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

import bot.sender as sender_mod
from bot.logic import get_version_name
from config import SUBJECT_MAX_LEN

logger = logging.getLogger("redmine_bot")


def _effective_portal_base() -> str:
    base = (sender_mod.PORTAL_BASE_URL or sender_mod.REDMINE_URL or "").strip().rstrip("/")
    if base:
        return base
    try:
        import bot.main as main_mod

        base = (main_mod.PORTAL_BASE_URL or main_mod.REDMINE_URL or "").strip().rstrip("/")
        if base:
            return base
    except Exception:
        pass
    # Сборка pytest и утилиты могут импортировать config до выставления REDMINE_URL в тестах;
    # getenv на момент вызова, а не константы из config при первом импорте.
    portal = (os.getenv("PORTAL_BASE_URL") or "").strip().rstrip("/")
    redmine = (os.getenv("REDMINE_URL") or "").strip().rstrip("/")
    return portal or redmine


def is_valid_http_issue_url(url: str) -> bool:
    value = (url or "").strip()
    if not value or value.startswith("/"):
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _status_display(issue: Any, catalogs: Any | None) -> str:
    raw = str(getattr(getattr(issue, "status", None), "name", "") or "")
    if catalogs is None:
        return raw
    try:
        sid = getattr(getattr(issue, "status", None), "id", None)
        if sid is not None:
            return str(catalogs.status_name(int(sid), default=raw))
    except Exception:
        pass
    return raw


def _priority_display(issue: Any, catalogs: Any | None) -> str:
    raw = str(getattr(getattr(issue, "priority", None), "name", "") or "")
    if catalogs is None:
        return raw
    try:
        pid = getattr(getattr(issue, "priority", None), "id", None)
        if pid is not None:
            return str(catalogs.priority_name(int(pid), default=raw))
    except Exception:
        pass
    return raw


def _version_display(issue: Any) -> str:
    v = get_version_name(issue)
    return str(v).strip() if v else ""


def _project_display(issue: Any) -> str:
    return str(getattr(getattr(issue, "project", None), "name", "") or "").strip() or "—"


def _assignee_display(issue: Any) -> str:
    return str(getattr(getattr(issue, "assigned_to", None), "name", "") or "").strip() or "—"


def _description_excerpt(issue: Any, limit: int = 300) -> str:
    raw = str(getattr(issue, "description", "") or "").strip()
    if not raw:
        return ""
    normalized = " ".join(raw.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _due_date_display(issue: Any) -> str:
    due = getattr(issue, "due_date", None)
    if due is None:
        return ""
    return str(due)


def _subject_display(issue: Any) -> str:
    raw = str(getattr(issue, "subject", "") or "").strip()
    if not raw:
        return ""
    if len(raw) <= SUBJECT_MAX_LEN:
        return raw
    return raw[: SUBJECT_MAX_LEN - 3].rstrip() + "..."


def build_issue_context(
    issue: Any,
    catalogs: Any | None,
    **extra: Any,
) -> dict[str, Any]:
    """Полный набор полей для issue-шаблонов; ``**extra`` переопределяет ключи (event_type, title, …)."""
    try:
        iid = int(getattr(issue, "id", 0) or 0)
    except Exception:
        iid = 0
    base_url = _effective_portal_base()
    issue_url = f"{base_url}/issues/{iid}" if base_url and iid else ""
    if iid and not issue_url:
        logger.warning("issue_url_base_missing issue_id=%s", iid)
    ctx: dict[str, Any] = {
        "issue_id": iid,
        "portal_base_url": base_url,
        "issue_url": issue_url,
        "subject": _subject_display(issue),
        "project_name": _project_display(issue),
        "status": _status_display(issue, catalogs),
        "priority": _priority_display(issue, catalogs),
        "version": _version_display(issue),
        "assignee_name": _assignee_display(issue),
        "description_excerpt": _description_excerpt(issue),
        "due_date": _due_date_display(issue),
        "emoji": "",
        "title": "",
        "event_type": "",
        "extra_text": "",
    }
    for k, v in extra.items():
        ctx[str(k)] = v
    return ctx


def preview_issue_context_demo(**overrides: Any) -> dict[str, Any]:
    """Демо-контекст с теми же ключами, что ``build_issue_context`` — для админ-предпросмотра.

    # Sync keys with build_issue_context (issue branch).
    """

    class _FakeIssue:
        id = 101
        subject = "Пример темы"
        project = type("PRJ", (), {"name": "Внутренний проект"})()
        status = type("S", (), {"id": 1, "name": "В работе"})()
        priority = type("P", (), {"id": 2, "name": "Нормальный"})()
        assigned_to = type("A", (), {"id": 10, "name": "Иван Петров"})()
        description = (
            "Краткое описание задачи для предпросмотра шаблонов в админке. "
            "Должно показывать, как выглядит усечение длинного текста."
        )
        due_date = "2026-04-30"
        fixed_version = type("V", (), {"name": "РЕД ОС 8"})()

    class _FakeCats:
        def status_name(self, rid: int, default: str = "?") -> str:
            return {1: "В работе"}.get(rid, default)

        def priority_name(self, rid: int, default: str = "?") -> str:
            return {2: "Нормальный"}.get(rid, default)

    fake_issue = _FakeIssue()
    ctx = build_issue_context(fake_issue, _FakeCats())
    ctx["portal_base_url"] = "https://redmine.example"
    ctx["issue_url"] = "https://redmine.example/issues/101"
    # Для шаблонов с точечной нотацией `issue.*` (предпросмотр в админке).
    ctx["issue"] = fake_issue
    ctx.update(
        {
            "emoji": "",
            "title": "Предпросмотр",
            "event_type": "comment",
            "extra_text": "Тестовое описание журнала",
        }
    )
    ctx.update(overrides)
    return ctx
