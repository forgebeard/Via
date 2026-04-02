"""
Отображение хвоста лога на странице «События»: новые строки сверху, дата ДД.ММ.ГГГГ ЧЧ:ММ:СС, без миллисекунд.

Префикс времени в формате logging `YYYY-MM-DD HH:MM:SS,mmm` обычно в **UTC** в контейнере Docker
(локаль процесса). По умолчанию парсим как UTC и переводим в BOT_TIMEZONE для показа.
Отключение: ADMIN_EVENTS_LOG_PARSE_AS_UTC=0 — тогда время в логе считается уже в BOT_TIMEZONE
(только убираем миллисекунды и переворачиваем порядок).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Стандартный asctime logging: 2026-04-02 06:21:14,317
_RE_ISO_TS = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:[.,]\d+)?(\s.*)?$",
)
# Уже записано админкой: 02.04.2026 09:21:14
_RE_DMY_TS = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})(\s.*)?$",
)


def _display_tz() -> ZoneInfo:
    name = (os.getenv("BOT_TIMEZONE") or "Europe/Moscow").strip() or "Europe/Moscow"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Moscow")


def admin_events_log_timestamp_now() -> str:
    """Метка времени для строк [ADMIN] в том же файле, что и «События» (ДД.ММ.ГГГГ, зона BOT_TIMEZONE)."""
    return datetime.now(_display_tz()).strftime("%d.%m.%Y %H:%M:%S")


def _parse_as_utc() -> bool:
    v = (os.getenv("ADMIN_EVENTS_LOG_PARSE_AS_UTC") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def reformat_log_line(line: str, *, display_tz: ZoneInfo, assume_utc: bool) -> str:
    """Одна строка: ISO+мс → ДД.ММ.ГГГГ ЧЧ:ММ:СС в display_tz; строки уже в ДД.ММ.ГГГГ — без изменений."""
    if not line.strip():
        return line
    m = _RE_ISO_TS.match(line)
    if m:
        date_s, time_s, tail = m.group(1), m.group(2), m.group(3) or ""
        try:
            naive = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return line
        if assume_utc:
            aware = naive.replace(tzinfo=timezone.utc)
        else:
            aware = naive.replace(tzinfo=display_tz)
        local = aware.astimezone(display_tz)
        return f"{local.strftime('%d.%m.%Y %H:%M:%S')}{tail}"
    if _RE_DMY_TS.match(line):
        return line
    return line


def format_events_log_for_ui(raw: str) -> str:
    """
    Хвост файла: переворачиваем строки (свежее сверху), форматируем время.
    Служебные сообщения об отсутствии файла не трогаем.
    """
    if not raw or raw.startswith("Файл лога не найден") or raw.startswith("Не удалось прочитать"):
        return raw
    assume_utc = _parse_as_utc()
    tz = _display_tz()
    lines = raw.splitlines()
    out = [reformat_log_line(line, display_tz=tz, assume_utc=assume_utc) for line in lines]
    out.reverse()
    return "\n".join(out)
