"""
Общая конфигурация тестов (фикстуры для pytest).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path
from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))  # Для import src.bot.main

# До импорта admin_main / database.session (иначе engine создастся без NullPool).
os.environ.setdefault("SQLALCHEMY_NULL_POOL", "1")

# Не писать лог в data/bot.log во время pytest — иначе админка «События» показывает
# строки из тестов (!room:server, Matrix send failed из моков и т.д.).
os.environ["LOG_TO_FILE"] = "0"


# ── Вспомогательные классы ──────────────────────────────────────────────

class _Named:
    """Объект с атрибутом .name (для status, priority, fixed_version)."""
    def __init__(self, name: str) -> None:
        self.name = name


class MockIssue:
    """Мок Redmine-задачи."""
    def __init__(
        self,
        issue_id: int = 12345,
        subject: str | None = None,
        version_name: str | None = None,
        status: str = "Новая",
        priority: str = "Нормальный",
        due_date: date | None = None,
        journals: list[MockJournal] | None = None,
    ) -> None:
        self.id: int = issue_id
        self.subject: str = subject if subject is not None else f"Тестовая задача #{issue_id}"
        self.status: _Named = _Named(status)
        self.priority: _Named = _Named(priority)
        self.due_date: date | None = due_date
        self.journals: list[MockJournal] = journals if journals is not None else []
        self.fixed_version: _Named | None = _Named(version_name) if version_name else None


class MockJournal:
    """Мок записи журнала Redmine."""
    def __init__(
        self,
        journal_id: int = 1,
        notes: str = "",
        user_name: str = "Тестовый пользователь",
        details: list[Any] | None = None,
    ) -> None:
        self.id: int = journal_id
        self.notes: str = notes
        self.user: _Named = _Named(user_name)
        self.details: list[Any] = details if details is not None else []


# ── Фикстуры ────────────────────────────────────────────────────────────

@pytest.fixture
def simple_issue() -> MockIssue:
    """Простая задача без версии."""
    return MockIssue(issue_id=7777, status="Новая")


@pytest.fixture
def issue_with_version() -> MockIssue:
    """Задача с версией РЕД Виртуализация 1.0."""
    return MockIssue(issue_id=8001, version_name="РЕД Виртуализация 1.0")


@pytest.fixture
def issue_with_journals() -> MockIssue:
    """Задача с тремя записями журнала (id=100, 200, 300)."""
    journals = [
        MockJournal(journal_id=100, notes="Первый комментарий"),
        MockJournal(journal_id=200, notes="Второй комментарий"),
        MockJournal(journal_id=300, notes="Третий комментарий"),
    ]
    return MockIssue(issue_id=4004, journals=journals)


@pytest.fixture
def rv_issue() -> MockIssue:
    """Задача со статусом 'Передано в работу.РВ' и версией Виртуализация."""
    return MockIssue(
        issue_id=8002,
        status="Передано в работу.РВ",
        version_name="РЕД Виртуализация 2.0",
    )


@pytest.fixture
def overdue_issue() -> MockIssue:
    """Просроченная задача (due_date = 3 дня назад)."""
    return MockIssue(
        issue_id=9999,
        due_date=date.today() - timedelta(days=3),
    )


@pytest.fixture
def mock_matrix_client() -> AsyncMock:
    """Мок Matrix-клиента с успешным room_send."""
    client = AsyncMock()
    success = MagicMock()
    success.event_id = "$fake_event_id"
    success.__class__ = type("RoomSendResponse", (), {})
    client.room_send = AsyncMock(return_value=success)
    return client


# Rate limiter теперь отключается через ADMIN_DISABLE_RATE_LIMITS=1 в CI env.
# Фикстура _no_admin_rate_limits_for_http_tests удалена — она не срабатывала
# т.к. _rate_limiter инициализируется до начала работы фикстур.
