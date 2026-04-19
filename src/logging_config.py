"""Конфигурация structured (JSON) логирования.

Если WANT_JSON_LOG=1 — логи в JSON-формате (для ELK/Loki).
Иначе — стандартный human-readable формат.

Метка %(asctime)s может отображаться в таймзоне сервиса (BOT_TIMEZONE из окружения),
см. apply_service_timezone_to_bot_logger / apply_service_timezone_to_admin_loggers.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None  # type: ignore[assignment]


def _want_json() -> bool:
    """Проверяет WANT_JSON_LOG=1 в окружении."""
    return os.getenv("WANT_JSON_LOG", "0").strip() == "1"


def resolve_service_tz_name(tz: str | None = None) -> str:
    """IANA-имя зоны для логов: аргумент → BOT_TIMEZONE → Москва."""
    n = (tz or os.environ.get("BOT_TIMEZONE") or "Europe/Moscow").strip()
    return n or "Europe/Moscow"


class ServiceTimezoneFormatter(logging.Formatter):
    """%(asctime)s в заданной IANA-зоне (не зависит от TZ контейнера)."""

    def __init__(self, *args, service_tz_name: str = "Europe/Moscow", **kwargs):
        super().__init__(*args, **kwargs)
        self._tz = ZoneInfo(service_tz_name)

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        if datefmt:
            try:
                return dt.strftime(datefmt)
            except (ValueError, TypeError):
                pass
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _make_json_formatter_with_tz(tz_name: str) -> logging.Formatter:
    """JsonFormatter с formatTime в service_tz (замыкание по tz_name)."""
    if jsonlogger is None:
        return ServiceTimezoneFormatter(
            "%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
            service_tz_name=tz_name,
        )

    class _ServiceTimezoneJsonFormatter(jsonlogger.JsonFormatter):
        def __init__(self, *args, **kwargs):
            self._tz = ZoneInfo(tz_name)
            super().__init__(*args, **kwargs)

        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=self._tz)
            if datefmt:
                try:
                    return dt.strftime(datefmt)
                except (ValueError, TypeError):
                    pass
            return dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    return _ServiceTimezoneJsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def get_log_formatter(service_tz_name: str | None = None) -> logging.Formatter:
    """Formatter для file/stream: asctime в service_tz."""
    tz = resolve_service_tz_name(service_tz_name)
    if _want_json() and jsonlogger is not None:
        return _make_json_formatter_with_tz(tz)
    return ServiceTimezoneFormatter(
        "%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
        service_tz_name=tz,
    )


def setup_json_logging(logger_name: str | None = None) -> None:
    """Настраивает JSON-логирование для root или указанного logger'а.

    Если python-json-logger недоступен — использует стандартный текстовый формат.
    """
    if not _want_json():
        return

    target = logging.getLogger(logger_name) if logger_name else logging.root

    # Удаляем существующие handlers (чтобы не дублировать)
    for handler in target.handlers[:]:
        target.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    tz = resolve_service_tz_name()
    handler.setFormatter(get_log_formatter(tz))
    target.addHandler(handler)


def apply_service_timezone_to_bot_logger(tz_name: str | None = None) -> None:
    """Переустанавливает formatter на всех handlers логгера redmine_bot."""
    tz = resolve_service_tz_name(tz_name)
    os.environ["BOT_TIMEZONE"] = tz
    log = logging.getLogger("redmine_bot")
    fmt = get_log_formatter(tz)
    for h in log.handlers:
        h.setFormatter(fmt)


def apply_service_timezone_to_admin_loggers(tz_name: str | None = None) -> None:
    """Handlers логгеров админки и root (uvicorn) — asctime в service_tz."""
    tz = resolve_service_tz_name(tz_name)
    os.environ["BOT_TIMEZONE"] = tz
    fmt = get_log_formatter(tz)
    seen: set[int] = set()
    for name in ("admin", "uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        for h in lg.handlers:
            hid = id(h)
            if hid in seen:
                continue
            seen.add(hid)
            h.setFormatter(fmt)
    root = logging.getLogger()
    for h in root.handlers:
        hid = id(h)
        if hid in seen:
            continue
        seen.add(hid)
        h.setFormatter(fmt)
