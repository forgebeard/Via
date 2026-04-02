"""Тесты журнала CRUD в файл «События» (src/admin/crud_events_log.py)."""

from __future__ import annotations

import pytest

from admin import crud_events_log as m


def test_want_admin_events_log_crud_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_EVENTS_LOG_CRUD", raising=False)
    monkeypatch.delenv("ADMIN_AUDIT_CRUD_DB", raising=False)
    assert m.want_admin_events_log_crud() is False
    monkeypatch.setenv("ADMIN_EVENTS_LOG_CRUD", "1")
    assert m.want_admin_events_log_crud() is True
    monkeypatch.setenv("ADMIN_EVENTS_LOG_CRUD", "true")
    assert m.want_admin_events_log_crud() is True


def test_want_admin_audit_crud_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_AUDIT_CRUD_DB", raising=False)
    monkeypatch.delenv("ADMIN_EVENTS_LOG_CRUD", raising=False)
    assert m.want_admin_audit_crud_db() is False
    monkeypatch.setenv("ADMIN_EVENTS_LOG_CRUD", "1")
    assert m.want_admin_audit_crud_db() is True
    monkeypatch.setenv("ADMIN_AUDIT_CRUD_DB", "0")
    assert m.want_admin_audit_crud_db() is False
    monkeypatch.setenv("ADMIN_AUDIT_CRUD_DB", "1")
    monkeypatch.setenv("ADMIN_EVENTS_LOG_CRUD", "0")
    assert m.want_admin_audit_crud_db() is True


def test_sanitize_redacts_secret_like_keys() -> None:
    d = m.sanitize_audit_details(
        {
            "name": "ok",
            "api_key": "should_not_appear",
            "extra": {"a": 1},
            "REDMINE_API_KEY": "x",
        }
    )
    assert d["name"] == "ok"
    assert d["api_key"] == "***REDACTED***"
    assert d["REDMINE_API_KEY"] == "***REDACTED***"
    assert d.get("extra") == "[omitted]"


def test_sanitize_truncates_long_strings() -> None:
    long_val = "a" * 200
    d = m.sanitize_audit_details({"note": long_val})
    assert len(d["note"]) <= m.MAX_DETAIL_SCALAR_LEN
    assert d["note"].endswith("...")


def test_format_crud_line_stable_order() -> None:
    line = m.format_crud_line(
        "bot_user",
        "create",
        "ad***",
        {"redmine_id": 7, "id": 1},
    )
    assert line.startswith("CRUD bot_user/create ")
    assert line.endswith(" by=ad***")
    assert "id=1" in line
    assert "redmine_id=7" in line
    # sorted keys: id before redmine_id
    assert line.index("id=1") < line.index("redmine_id=7")


def test_actor_label_for_crud_log() -> None:
    class U:
        login = "admin"

    assert m.actor_label_for_crud_log(U()) == "ad***"
    assert m.actor_label_for_crud_log(None) == "unknown"
