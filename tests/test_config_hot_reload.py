"""Юнит-тесты bot/config_hot_reload.py (без БД)."""

from __future__ import annotations

import bot.config_hot_reload as hr


def test_users_fingerprint_strips_cipher_bytes():
    users = [
        {
            "redmine_id": 1,
            "room": "!r:s",
            "_redmine_key_cipher": b"abc",
            "_redmine_key_nonce": b"def",
        }
    ]
    fp = hr._users_fingerprint(users)
    assert "_redmine_key_cipher" not in fp[0]
    assert fp[0]["_has_rm_key"] is True
