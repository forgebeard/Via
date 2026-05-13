"""Тесты rules-only маршрутизации журнального движка."""

from __future__ import annotations

from types import SimpleNamespace

from bot.journal_handlers import infer_event_type
from bot.routing import resolve_policy_target_rooms


def _issue(*, status_id=11, version_id=21, priority_id=31, assignee_id=42):
    st = SimpleNamespace(id=status_id, name="Статус")
    fv = SimpleNamespace(id=version_id, name="Версия") if version_id is not None else None
    asg = SimpleNamespace(id=assignee_id, name="User")
    return SimpleNamespace(
        id=100,
        status=st,
        fixed_version=fv,
        assigned_to=asg,
        priority=SimpleNamespace(id=priority_id, name="Нормальный"),
    )


def test_infer_event_type_comment_vs_assigned():
    j_notes = SimpleNamespace(id=1, notes="hi", details=[])
    assert infer_event_type(j_notes) == "comment"

    j_asg = SimpleNamespace(
        id=2,
        notes="",
        details=[{"property": "assigned_to_id", "old_value": "1", "new_value": "2"}],
    )
    assert infer_event_type(j_asg) == "assigned"


def _cfg_user(**kwargs):
    base = {
        "id": 1,
        "redmine_id": 1,
        "room": "!u1:example.org",
        "notify": ["issue_updated"],
        "versions": ["all"],
        "priorities": ["all"],
    }
    base.update(kwargs)
    return base


def _cfg_group(**kwargs):
    base = {
        "group_id": 7,
        "room": "!g7:example.org",
        "notify": ["issue_updated"],
        "versions": ["all"],
        "priorities": ["all"],
    }
    base.update(kwargs)
    return base


def test_policy_routing_attr_only_union_and_dedup():
    routes = {
        "routing_policies": [
            {
                "id": 1,
                "action_kind": "updated",
                "status_ids": [11],
                "version_ids": [21],
                "priority_ids": [31],
                "notification_type_key": "issue_updated",
                "recipient_modes": ["match_rooms"],
            },
            {
                "id": 2,
                "action_kind": "updated",
                "status_ids": [],
                "version_ids": [],
                "priority_ids": [],
                "notification_type_key": "issue_updated",
                "recipient_modes": ["match_rooms"],
            },
        ]
    }
    users = [_cfg_user()]
    groups = [_cfg_group()]
    res = resolve_policy_target_rooms(
        _issue(), routes, action_kind="updated", users=users, groups=groups
    )
    assert sorted(res.matched_policy_ids) == [1, 2]
    assert res.deliveries == (
        ("!u1:example.org", "issue_updated"),
        ("!g7:example.org", "issue_updated"),
    )
    assert sorted(res.room_ids) == ["!g7:example.org", "!u1:example.org"]


def test_policy_routing_self_action_skips_only_actor_user():
    routes = {
        "routing_policies": [
            {
                "id": 1,
                "action_kind": "updated",
                "status_ids": [],
                "version_ids": [],
                "priority_ids": [],
                "notification_type_key": "issue_updated",
                "recipient_modes": ["match_rooms"],
            },
        ]
    }
    users = [_cfg_user(redmine_id=10), _cfg_user(id=2, redmine_id=11, room="!u2:example.org")]
    groups = [_cfg_group()]
    res = resolve_policy_target_rooms(
        _issue(),
        routes,
        action_kind="updated",
        users=users,
        groups=groups,
        actor_redmine_id=10,
    )
    assert ("!u1:example.org", "issue_updated") not in res.deliveries
    assert ("!u2:example.org", "issue_updated") in res.deliveries
    assert ("!g7:example.org", "issue_updated") in res.deliveries
    assert sorted(res.room_ids) == ["!g7:example.org", "!u2:example.org"]


def test_policy_routing_unknown_type_falls_back_to_issue_updated():
    routes = {
        "routing_policies": [
            {
                "id": 1,
                "action_kind": "created",
                "status_ids": [],
                "version_ids": [],
                "priority_ids": [],
                "notification_type_key": "unexpected_key",
                "recipient_modes": ["match_rooms"],
            },
        ]
    }
    users = [_cfg_user(notify=["issue_updated"])]
    groups = [_cfg_group()]
    res = resolve_policy_target_rooms(
        _issue(), routes, action_kind="created", users=users, groups=groups
    )
    assert res.deliveries == (
        ("!u1:example.org", "issue_updated"),
        ("!g7:example.org", "issue_updated"),
    )
    assert sorted(res.room_ids) == ["!g7:example.org", "!u1:example.org"]


def test_policy_routing_recipient_modes_assignee_and_watchers():
    routes = {
        "routing_policies": [
            {
                "id": 3,
                "action_kind": "updated",
                "status_ids": [],
                "version_ids": [],
                "priority_ids": [],
                "notification_type_key": "issue_updated",
                "recipient_modes": ["assignee", "watchers"],
            }
        ]
    }
    assignee_cfg = _cfg_user(redmine_id=42, room="!asg:example.org")
    watcher_cfgs = [
        _cfg_user(id=3, redmine_id=50, room="!w1:example.org"),
        _cfg_user(id=4, redmine_id=51, room="!w2:example.org"),
    ]
    res = resolve_policy_target_rooms(
        _issue(),
        routes,
        action_kind="updated",
        users=[],
        groups=[],
        assignee_cfg=assignee_cfg,
        watcher_cfgs=watcher_cfgs,
        actor_redmine_id=50,
    )
    assert res.deliveries == (
        ("!asg:example.org", "issue_updated"),
        ("!w2:example.org", "issue_updated"),
    )
