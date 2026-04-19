"""Тесты маршрутизации журнального движка (без Matrix/БД)."""

from __future__ import annotations

from types import SimpleNamespace

from bot.journal_handlers import infer_event_type
from bot.routing import get_matching_route


def _issue(*, status="Передано в работу.РВ", version_name="РЕД ОС 8", assignee_id=42):
    st = SimpleNamespace(name=status)
    fv = SimpleNamespace(name=version_name) if version_name else None
    asg = SimpleNamespace(id=assignee_id, name="User")
    return SimpleNamespace(id=100, status=st, fixed_version=fv, assigned_to=asg, priority=SimpleNamespace(name="Нормальный"))


def test_user_version_route_wins_over_global():
    assignee = {
        "id": 1,
        "redmine_id": 42,
        "room": "!dm:example.org",
        "version_routes": [
            {
                "key": "РЕД ОС",
                "room": "!userver:example.org",
                "priority": 10,
                "sort_order": 0,
                "notify_on_assignment": True,
                "route_source": "user_version_route",
                "route_id": 1,
            }
        ],
    }
    routes = {
        "version_routes_global": [
            {
                "version_key": "РЕД ОС",
                "room_id": "!global:example.org",
                "priority": 10,
                "sort_order": 0,
                "notify_on_assignment": True,
                "route_source": "version_room_route",
                "route_id": 2,
            }
        ],
        "status_routes": [],
    }
    m = get_matching_route(_issue(), routes, assignee, groups=[])
    assert m is not None
    assert m.room_id == "!userver:example.org"
    assert m.source_table == "user_version_route"


def test_global_version_when_no_user_route():
    assignee = {"id": 1, "redmine_id": 42, "room": "!x:x", "version_routes": []}
    routes = {
        "version_routes_global": [
            {
                "version_key": "Вирт",
                "room_id": "!virt:example.org",
                "priority": 5,
                "sort_order": 0,
                "notify_on_assignment": True,
                "route_source": "version_room_route",
                "route_id": 9,
            }
        ],
        "status_routes": [],
    }
    iss = _issue(version_name="РЕД Виртуализация")
    m = get_matching_route(iss, routes, assignee, groups=[])
    assert m is not None
    assert m.room_id == "!virt:example.org"


def test_status_route():
    assignee = {"id": 1, "redmine_id": 42, "room": "!x:x", "version_routes": [], "group_id": None}
    routes = {
        "version_routes_global": [],
        "status_routes": [
            {
                "status_key": "Передано в работу.РВ",
                "room_id": "!rv:example.org",
                "priority": 1,
                "sort_order": 0,
                "notify_on_assignment": True,
                "route_source": "status_room_route",
                "route_id": 3,
            }
        ],
    }
    m = get_matching_route(_issue(), routes, assignee, groups=[])
    assert m is not None
    assert m.room_id == "!rv:example.org"


def test_support_group_fallback():
    assignee = {
        "id": 1,
        "redmine_id": 42,
        "room": "!dm:x",
        "version_routes": [],
        "group_id": 7,
    }
    groups = [
        {
            "group_id": 7,
            "room": "!group7:x",
            "notify": ["all"],
            "versions": ["all"],
            "priorities": ["all"],
            "notify_on_assignment": True,
        }
    ]
    m = get_matching_route(_issue(version_name="Unknown"), {}, assignee, groups=groups)
    assert m is not None
    assert m.room_id == "!group7:x"
    assert m.source_table == "support_groups"


def test_infer_event_type_comment_vs_assigned():
    j_notes = SimpleNamespace(id=1, notes="hi", details=[])
    assert infer_event_type(j_notes) == "comment"

    j_asg = SimpleNamespace(
        id=2,
        notes="",
        details=[{"property": "assigned_to_id", "old_value": "1", "new_value": "2"}],
    )
    assert infer_event_type(j_asg) == "assigned"
