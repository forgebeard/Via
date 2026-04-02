"""Парсинг и валидация онбординга Matrix (без реальной БД/Matrix)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import matrix_onboarding as mob


class TestParseWorkHours:
    def test_default_empty(self):
        assert mob._parse_work_hours("") == ("09:00-18:00", None)

    def test_valid(self):
        assert mob._parse_work_hours("09:30-18:45") == ("09:30-18:45", None)

    def test_invalid(self):
        wh, err = mob._parse_work_hours("9-5")
        assert wh is None
        assert err


class TestParseWorkDays:
    def test_default(self):
        assert mob._parse_work_days("") == ([0, 1, 2, 3, 4], None)

    def test_list(self):
        assert mob._parse_work_days("0, 6") == ([0, 6], None)

    def test_bad_day(self):
        d, err = mob._parse_work_days("9")
        assert d is None
        assert err


class TestParseNotify:
    def test_all(self):
        assert mob._parse_notify("all") == (["all"], None)
        assert mob._parse_notify("ВСЕ") == (["all"], None)

    def test_subset(self):
        assert mob._parse_notify("new, overdue") == (["new", "overdue"], None)

    def test_unknown(self):
        n, err = mob._parse_notify("nosuch")
        assert n is None
        assert err


@pytest.mark.asyncio
async def test_validate_redmine_api_key_ok():
    import io

    payload = json.dumps({"user": {"id": 42, "login": "u"}}).encode()
    bio = io.BytesIO(payload)

    with patch("matrix_onboarding.urllib.request.urlopen", return_value=bio):
        user, err = await mob.validate_redmine_api_key("https://rm.test/", "secret-key-here")
    assert err is None
    assert user["id"] == 42


@pytest.mark.asyncio
async def test_validate_redmine_api_key_http_error():
    import urllib.error

    def _boom(*a, **k):
        raise urllib.error.HTTPError("url", 403, "Forbidden", hdrs=None, fp=None)

    with patch("matrix_onboarding.urllib.request.urlopen", side_effect=_boom):
        user, err = await mob.validate_redmine_api_key("https://rm.test/", "bad")
    assert user is None
    assert err == "http_403"


def test_redmine_client_for_user_fallback_without_cipher():
    import bot
    from redminelib import Redmine

    grm = Redmine("https://x", key="global")
    cfg = {"redmine_id": 1, "room": "!r:s"}
    assert bot.redmine_client_for_user(grm, cfg) is grm


def test_redmine_client_for_user_decrypt(monkeypatch):
    import bot
    from redminelib import Redmine

    monkeypatch.setattr(bot, "_get_bot_master_key", lambda: b"x" * 32)
    monkeypatch.setattr(
        bot,
        "REDMINE_URL",
        "https://redmine.test",
    )

    from security import encrypt_secret

    enc = encrypt_secret("personal-key-123", b"x" * 32)
    cfg = {
        "redmine_id": 1,
        "room": "!r:s",
        "_redmine_key_cipher": enc.ciphertext,
        "_redmine_key_nonce": enc.nonce,
    }
    grm = Redmine("https://redmine.test", key="global")
    u = bot.redmine_client_for_user(grm, cfg)
    assert u is not grm
    assert u is not None
