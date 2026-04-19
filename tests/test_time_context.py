"""Тесты bot/time_context.py: контекст personal vs group_room."""

from __future__ import annotations

from bot.time_context import notify_context_for_room, resolve_effective_zone
from utils import BOT_TZ


def test_resolve_personal_user_timezone():
    z = resolve_effective_zone({"timezone": "Indian/Antananarivo"}, context="personal")
    assert str(z) == "Indian/Antananarivo"


def test_resolve_personal_fallback_service():
    z = resolve_effective_zone({}, context="personal")
    assert z == BOT_TZ


def test_resolve_group_room_prefers_group_timezone():
    z = resolve_effective_zone(
        {"group_timezone": "Europe/Moscow", "timezone": "Indian/Antananarivo"},
        context="group_room",
    )
    assert str(z) == "Europe/Moscow"


def test_resolve_group_standalone_uses_top_level_timezone():
    z = resolve_effective_zone({"timezone": "Europe/Moscow", "group_id": 1}, context="group_room")
    assert str(z) == "Europe/Moscow"


def test_notify_context_member_group_room():
    assert (
        notify_context_for_room(
            {
                "group_room": "!grp:example.org",
                "room": "!dm:example.org",
            },
            "!grp:example.org",
        )
        == "group_room"
    )


def test_notify_context_member_personal_dm():
    assert (
        notify_context_for_room(
            {
                "group_room": "!grp:example.org",
                "room": "!dm:example.org",
            },
            "!dm:example.org",
        )
        == "personal"
    )


def test_notify_context_standalone_group():
    assert (
        notify_context_for_room(
            {
                "group_id": 1,
                "room": "!grp:example.org",
            },
            "!grp:example.org",
        )
        == "group_room"
    )
