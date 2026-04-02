"""Тесты форматирования блока «Сервис» на дашборде."""

from datetime import datetime, timezone

import pytest

from dash_service_display import (
    bot_status_label_ru,
    format_local_started_at,
    humanize_uptime_ru,
    parse_docker_started_at,
    service_card_context,
)


def test_parse_docker_started_at_z_and_fraction():
    dt = parse_docker_started_at("2026-03-15T10:20:30.123456789Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 15


def test_parse_docker_started_at_zero_sentinel():
    assert parse_docker_started_at("0001-01-01T00:00:00Z") is None


def test_humanize_skips_zero_units():
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 3, 14, 30, 45, tzinfo=timezone.utc)
    s = humanize_uptime_ru(base, now)
    assert "дн" in s or "день" in s or "дня" in s or "дней" in s
    assert "час" in s
    assert "минут" in s
    assert "секунд" in s or "секунда" in s or "секунды" in s


def test_humanize_no_trailing_zero_seconds():
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    s = humanize_uptime_ru(base, now)
    assert "1 час" in s or "1 часа" in s
    assert "0 секунд" not in s


def test_bot_status_restarting():
    assert bot_status_label_ru({"docker_status": "restarting", "running": False}) == "Рестарт"


def test_format_local_started_at_dmy():
    dt = datetime(2026, 4, 2, 6, 42, 44, tzinfo=timezone.utc)
    assert format_local_started_at(dt, "Europe/Moscow") == "02.04.2026 09:42:44"


def test_service_card_stopped_no_uptime():
    docker = {
        "state": "stopped",
        "running": False,
        "docker_status": "exited",
        "started_at": "2026-01-01T00:00:00Z",
        "container_name": "x",
    }
    ctx = service_card_context(docker, {"error_count": 0}, "Europe/Moscow")
    assert ctx["bot_status_label"] == "Выключен"
    assert ctx["uptime_display"] == "—"
    assert ctx["started_display"] == "—"


@pytest.mark.parametrize(
    ("running", "ds", "label"),
    [
        (True, "running", "Включен"),
        (False, "exited", "Выключен"),
        (False, "paused", "Пауза"),
    ],
)
def test_bot_status_labels(running, ds, label):
    assert bot_status_label_ru({"running": running, "docker_status": ds, "state": "stopped"}) == label
