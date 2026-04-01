"""Тесты src/database/load_config.py (user_orm_to_cfg)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from database.load_config import user_orm_to_cfg  # noqa: E402


class _FakeUser:
    def __init__(self) -> None:
        self.redmine_id = 42
        self.room = "!personal:matrix"
        self.notify = ["all"]
        self.group_id = 7
        self.work_hours = "08:00-09:00"
        self.work_days = [0, 1]
        self.dnd = False


class _FakeGroup:
    def __init__(self) -> None:
        self.id = 7
        self.name = "Команда"
        self.room_id = "!group:matrix"
        self.timezone = "Europe/Moscow"
        self.notify = ["new", "overdue"]
        self.work_hours = "10:00-19:00"
        self.work_days = [0, 1, 2, 3, 4]
        self.dnd = True


def test_user_orm_to_cfg_includes_group_delivery() -> None:
    u = _FakeUser()
    g = _FakeGroup()
    cfg = user_orm_to_cfg(u, {g.id: g})
    assert cfg["group_room"] == "!group:matrix"
    gd = cfg.get("group_delivery")
    assert isinstance(gd, dict)
    assert gd["notify"] == ["new", "overdue"]
    assert gd["work_hours"] == "10:00-19:00"
    assert gd["work_days"] == [0, 1, 2, 3, 4]
    assert gd["dnd"] is True
    assert cfg["work_hours"] == "08:00-09:00"
