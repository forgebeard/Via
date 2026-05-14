"""Тесты для src/database/load_config.py — user_orm_to_cfg."""

from __future__ import annotations

from unittest.mock import MagicMock

import database.load_config as lc


def _make_user(**kwargs):
    """Создаёт мок BotUser с заданными атрибутами."""
    u = MagicMock()
    u.id = kwargs.get("id", 1)
    u.redmine_id = kwargs.get("redmine_id", 100)
    u.room = kwargs.get("room", "!room:server")
    u.notify = kwargs.get("notify", ["all"])
    u.group_id = kwargs.get("group_id")
    u.timezone = kwargs.get("timezone")
    u.work_hours = kwargs.get("work_hours")
    u.work_days = kwargs.get("work_days")
    u.dnd = kwargs.get("dnd", False)
    u.redmine_api_key_ciphertext = kwargs.get("ciphertext")
    u.redmine_api_key_nonce = kwargs.get("nonce")
    return u


def _make_group(**kwargs):
    """Создаёт мок SupportGroup."""
    g = MagicMock()
    g.id = kwargs.get("id", 1)
    g.name = kwargs.get("name", "Test Group")
    g.room_id = kwargs.get("room_id", "!grp:server")
    g.timezone = kwargs.get("timezone")
    g.notify = kwargs.get("notify", ["all"])
    g.work_hours = kwargs.get("work_hours")
    g.work_days = kwargs.get("work_days")
    g.dnd = kwargs.get("dnd", False)
    return g


class TestUserOrmToCfg:
    """user_orm_to_cfg: преобразование ORM пользователя в конфиг."""

    def test_minimal_user(self):
        user = _make_user()
        result = lc.user_orm_to_cfg(user, {})
        assert result["redmine_id"] == 100
        assert result["room"] == "!room:server"
        assert result["notify"] == ["all"]
        assert "group_id" not in result

    def test_user_with_group(self):
        user = _make_user(group_id=1)
        group = _make_group(id=1, name="Dev", room_id="!dev:server")
        result = lc.user_orm_to_cfg(user, {1: group})
        assert result["group_id"] == 1
        assert result["group_name"] == "Dev"
        assert result["group_room"] == "!dev:server"

    def test_user_with_group_timezone(self):
        user = _make_user(group_id=1)
        group = _make_group(id=1, timezone="Europe/Moscow")
        result = lc.user_orm_to_cfg(user, {1: group})
        assert result["group_timezone"] == "Europe/Moscow"

    def test_user_timezone_independent_of_group(self):
        user = _make_user(group_id=1, timezone="Indian/Antananarivo")
        group = _make_group(id=1, timezone="Europe/Moscow")
        result = lc.user_orm_to_cfg(user, {1: group})
        assert result["timezone"] == "Indian/Antananarivo"
        assert result["group_timezone"] == "Europe/Moscow"

    def test_user_with_group_delivery(self):
        user = _make_user(group_id=1)
        group = _make_group(
            id=1,
            notify=["new", "issue_updated"],
            work_hours="09:00-18:00",
            work_days=[0, 1, 2, 3, 4],
            dnd=True,
        )
        result = lc.user_orm_to_cfg(user, {1: group})
        assert result["group_delivery"]["notify"] == ["new", "issue_updated"]
        assert result["group_delivery"]["work_hours"] == "09:00-18:00"
        assert result["group_delivery"]["work_days"] == [0, 1, 2, 3, 4]
        assert result["group_delivery"]["dnd"] is True

    def test_user_work_hours_override(self):
        user = _make_user(group_id=1, work_hours="10:00-19:00")
        group = _make_group(id=1, work_hours="09:00-18:00")
        result = lc.user_orm_to_cfg(user, {1: group})
        # work_hours пользователя должен быть в корне, group_delivery — от группы
        assert result["work_hours"] == "10:00-19:00"
        assert result["group_delivery"]["work_hours"] == "09:00-18:00"

    def test_user_work_days(self):
        user = _make_user(work_days=[1, 3, 5])
        result = lc.user_orm_to_cfg(user, {})
        assert result["work_days"] == [1, 3, 5]

    def test_user_dnd(self):
        user = _make_user(dnd=True)
        result = lc.user_orm_to_cfg(user, {})
        assert result["dnd"] is True

    def test_encrypted_key_included(self):
        user = _make_user(ciphertext=b"encrypted", nonce=b"nonce123")
        result = lc.user_orm_to_cfg(user, {})
        assert result["_redmine_key_cipher"] == b"encrypted"
        assert result["_redmine_key_nonce"] == b"nonce123"

    def test_no_group_no_group_fields(self):
        user = _make_user()
        result = lc.user_orm_to_cfg(user, {})
        assert "group_name" not in result
        assert "group_room" not in result
        assert "group_delivery" not in result
        assert "group_timezone" not in result

    def test_group_not_in_dict_ignored(self):
        user = _make_user(group_id=999)
        result = lc.user_orm_to_cfg(user, {})
        assert result["group_id"] == 999
        assert "group_name" not in result

    def test_notify_not_list_defaults_all(self):
        user = _make_user(notify=None)
        result = lc.user_orm_to_cfg(user, {})
        assert result["notify"] == ["all"]

    def test_group_notify_not_list_defaults_all(self):
        user = _make_user(group_id=1)
        group = _make_group(id=1, notify=None)
        result = lc.user_orm_to_cfg(user, {1: group})
        assert result["group_delivery"]["notify"] == ["all"]


class TestGroupOrmToCfg:
    def test_timezone_included(self):
        group = _make_group(id=1, timezone="Europe/Moscow")
        result = lc.group_orm_to_cfg(group)
        assert result["timezone"] == "Europe/Moscow"
