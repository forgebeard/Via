"""Тесты форматирования хвоста лога на странице «События»."""

from __future__ import annotations

import pytest

from events_log_display import (
    admin_events_log_timestamp_now,
    format_events_log_for_ui,
    reformat_log_line,
)
from zoneinfo import ZoneInfo


def test_reformat_iso_strips_ms_and_converts_utc_to_moscow(monkeypatch):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    monkeypatch.setenv("ADMIN_EVENTS_LOG_PARSE_AS_UTC", "1")
    tz = ZoneInfo("Europe/Moscow")
    line = "2026-04-02 06:21:14,317 [ADMIN] Docker bot/stop ok"
    out = reformat_log_line(line, display_tz=tz, assume_utc=True)
    assert out == "02.04.2026 09:21:14 [ADMIN] Docker bot/stop ok"
    assert ",317" not in out


def test_reformat_iso_no_assume_utc(monkeypatch):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    tz = ZoneInfo("Europe/Moscow")
    line = "2026-04-02 09:21:14 [ADMIN] x"
    out = reformat_log_line(line, display_tz=tz, assume_utc=False)
    assert out == "02.04.2026 09:21:14 [ADMIN] x"


def test_reformat_dmy_unchanged(monkeypatch):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    tz = ZoneInfo("Europe/Moscow")
    line = "02.04.2026 12:00:00 [ADMIN] login"
    assert reformat_log_line(line, display_tz=tz, assume_utc=True) == line


def test_format_events_log_reverses_and_formats(monkeypatch):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    monkeypatch.setenv("ADMIN_EVENTS_LOG_PARSE_AS_UTC", "1")
    raw = (
        "2026-04-02 06:00:00,1 a\n"
        "2026-04-02 07:00:00,2 b"
    )
    text = format_events_log_for_ui(raw)
    lines = text.splitlines()
    assert len(lines) == 2
    # После reverse: сначала более поздняя по файлу строка (07:00 UTC → 10:00 MSK).
    assert "b" in lines[0] and "10:00:00" in lines[0]
    assert "a" in lines[1] and "09:00:00" in lines[1]


def test_format_events_log_passes_through_missing_file_message():
    raw = "Файл лога не найден: /x\nhint"
    assert format_events_log_for_ui(raw) == raw


def test_admin_events_log_timestamp_now_respects_bot_timezone(monkeypatch):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    s = admin_events_log_timestamp_now()
    assert len(s) == 19
    assert s[2] == "." and s[5] == "."


@pytest.mark.parametrize(
    "off",
    ("0", "false", "no", "off"),
)
def test_parse_as_utc_env_off(monkeypatch, off):
    monkeypatch.setenv("BOT_TIMEZONE", "Europe/Moscow")
    monkeypatch.setenv("ADMIN_EVENTS_LOG_PARSE_AS_UTC", off)
    line = "2026-04-02 09:21:14 [ADMIN] x"
    text = format_events_log_for_ui(line)
    assert "09:21:14" in text
