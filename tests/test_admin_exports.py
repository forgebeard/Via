"""Интеграционный тест: проверяет что все имена, используемые route файлами,
доступны через admin.main (через _admin())."""

from __future__ import annotations

import re
from pathlib import Path

import admin.main as admin_main


def _get_route_files() -> list[Path]:
    """Находит все route файлы."""
    routes_dir = Path(__file__).resolve().parents[1] / "src" / "admin" / "routes"
    return sorted(routes_dir.glob("*.py"))


def _find_admin_calls(route_code: str) -> set[str]:
    """Находит все обращения admin.X(...) в коде route файла (функции/методы)."""
    calls = set()
    # admin.some_name( — вызов функции
    for m in re.finditer(r"admin\.(\w+)\s*\(", route_code):
        name = m.group(1)
        # Исключаем Python internals и очевидные модули
        if name in ("__file__", "__name__", "__doc__", "__package__"):
            continue
        # Исключаем модули и SQLAlchemy internals
        if name in (
            "api_schemas",
            "env_manager",
            "helpers",
            "main",
            "helpers_ext",
            "middleware",
            "db_config",
            "crud_events_log",
            "or_",
            "update",
            "scalar_one_or_none",
            "sync_database_url_for_alembic",
        ):
            continue
        calls.add(name)
    return calls


class TestAllAdminExportsAvailable:
    """Все admin.X из route файлов должны быть доступны в admin.main."""

    def test_all_route_admin_calls_exist_in_main(self):
        """Проверяет что каждое admin.X из route файлов существует в admin.main."""
        missing: dict[str, list[str]] = {}  # name -> [files]

        for route_file in _get_route_files():
            code = route_file.read_text(encoding="utf-8")
            calls = _find_admin_calls(code)
            for name in calls:
                if not hasattr(admin_main, name):
                    missing.setdefault(name, []).append(route_file.name)

        if missing:
            msg = "Следующие admin.X не найдены в admin.main:\n"
            for name, files in sorted(missing.items()):
                msg += f"  • {name} — используется в: {', '.join(files)}\n"
            msg += "\nДобавьте имя в admin/_exports.py"
            raise AssertionError(msg)
