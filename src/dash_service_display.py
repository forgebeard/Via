"""
Отображение блока «Сервис» на дашборде: время старта контейнера из Docker, uptime, подписи на русском.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def parse_docker_started_at(raw: str) -> datetime | None:
    """Разбор StartedAt из Docker inspect (RFC3339, наносекунды)."""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.startswith("0001-01-01"):
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    def _norm(m: re.Match[str]) -> str:
        base, frac, tz = m.group(1), m.group(2), m.group(3) or "+00:00"
        if frac:
            digits = (frac[1:] + "000000")[:6]
            return f"{base}.{digits}{tz}"
        return f"{base}{tz}"

    s2 = re.sub(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2})$", _norm, s)
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ru_unit(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n)) % 100
    n1 = n % 10
    if 10 < n < 20:
        return many
    if n1 == 1:
        return one
    if 1 < n1 < 5:
        return few
    return many


def humanize_uptime_ru(started_at: datetime | None, now: datetime | None = None) -> str:
    """
    Длительность от started_at до now; только ненулевые старшие единицы.
    Порядок: год (≈365д), месяц (≈30д), день, час, минута, секунда (онлайн-обновление).
    """
    if started_at is None:
        return "—"
    now = now or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    sec_total = int((now - started_at.astimezone(timezone.utc)).total_seconds())
    if sec_total < 0:
        return "—"
    if sec_total == 0:
        return "0 секунд"

    parts: list[str] = []
    y_sec = 365 * 86400
    mo_sec = 30 * 86400

    y = sec_total // y_sec
    sec_total %= y_sec
    mo = sec_total // mo_sec
    sec_total %= mo_sec
    d = sec_total // 86400
    sec_total %= 86400
    h = sec_total // 3600
    sec_total %= 3600
    m = sec_total // 60
    s = sec_total % 60

    if y:
        parts.append(f"{y} {_ru_unit(y, 'год', 'года', 'лет')}")
    if mo:
        parts.append(f"{mo} {_ru_unit(mo, 'месяц', 'месяца', 'месяцев')}")
    if d:
        parts.append(f"{d} {_ru_unit(d, 'день', 'дня', 'дней')}")
    if h:
        parts.append(f"{h} {_ru_unit(h, 'час', 'часа', 'часов')}")
    if m:
        parts.append(f"{m} {_ru_unit(m, 'минута', 'минуты', 'минут')}")
    if s > 0:
        parts.append(f"{s} {_ru_unit(s, 'секунда', 'секунды', 'секунд')}")
    if not parts:
        parts.append("0 секунд")
    return " ".join(parts)


def format_local_started_at(started_at: datetime | None, tz_name: str) -> str:
    if started_at is None:
        return "—"
    try:
        tz = ZoneInfo((tz_name or "Europe/Moscow").strip() or "Europe/Moscow")
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    local = started_at.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M:%S")


def bot_status_label_ru(docker: dict[str, Any]) -> str:
    """Короткая подпись состояния бота для UI."""
    if docker.get("state") == "error":
        return "Ошибка Docker"
    if docker.get("state") == "not_found":
        return "Контейнер не найден"
    ds = str(docker.get("docker_status") or "").lower()
    if ds == "restarting":
        return "Рестарт"
    if docker.get("running") is True or ds == "running":
        return "Включен"
    if ds in ("exited", "dead"):
        return "Выключен"
    if ds == "paused":
        return "Пауза"
    if ds in ("created", "removing"):
        return "Запуск…"
    if docker.get("running") is False:
        return "Выключен"
    return "Неизвестно"


def service_card_context(docker: dict[str, Any], cycle: dict[str, Any], tz_name: str) -> dict[str, Any]:
    """
    Контекст для partial «Сервис»: подписи, дата старта и uptime только пока контейнер
    запущен или в состоянии перезапуска (по данным Docker).
    """
    started = parse_docker_started_at(str(docker.get("started_at") or ""))
    ds = str(docker.get("docker_status") or "").lower()
    running = bool(docker.get("running"))
    restarting = ds == "restarting"
    st = str(docker.get("state") or "")

    if st in ("error", "not_found"):
        started_disp = "—"
        uptime_disp = "—"
    elif running or restarting:
        started_disp = format_local_started_at(started, tz_name) if started else "—"
        uptime_disp = humanize_uptime_ru(started) if started else "—"
    else:
        started_disp = "—"
        uptime_disp = "—"

    err_n = 0
    try:
        err_n = int(cycle.get("error_count") or 0)
    except (TypeError, ValueError):
        err_n = 0

    return {
        "bot_status_label": bot_status_label_ru(docker),
        "started_display": started_disp,
        "uptime_display": uptime_disp,
        "error_count": err_n,
    }
