from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.journal_handlers import handle_journal_entry
from bot.routing import PolicyRoutingResult


def _issue():
    return SimpleNamespace(
        id=501,
        subject="Issue",
        status=SimpleNamespace(id=1, name="Новая"),
        priority=SimpleNamespace(id=2, name="Normal"),
        fixed_version=SimpleNamespace(id=3, name="V1"),
        assigned_to=SimpleNamespace(id=10, name="Ivan"),
    )


def _journal():
    return SimpleNamespace(
        id=11,
        notes="",
        user=SimpleNamespace(id=10, name="Ivan"),
        details=[],
    )


@pytest.mark.asyncio
async def test_handle_journal_entry_skips_when_dedup_blocks() -> None:
    client = AsyncMock()
    session = AsyncMock()
    issue = _issue()
    journal = _journal()
    assignee_cfg = {"id": 1, "redmine_id": 10, "room": "!r:example", "notify": ["all"]}
    with (
        patch("bot.journal_handlers.watcher_cfgs_for_routing", new=AsyncMock(return_value=[])),
        patch(
            "bot.journal_handlers.resolve_policy_target_rooms",
            return_value=PolicyRoutingResult(
                deliveries=(("!r:example", "issue_updated"),),
                matched_policy_ids=(1,),
                action_kind="updated",
            ),
        ),
        patch("bot.journal_handlers.can_notify", return_value=True),
        patch(
            "bot.journal_handlers.should_send_journal_notification",
            new=AsyncMock(return_value=False),
        ),
        patch("bot.journal_handlers.journal_render_send_or_dlq", new=AsyncMock()) as send_mock,
    ):
        await handle_journal_entry(
            client,
            session,
            issue=issue,
            journal=journal,
            assignee_cfg=assignee_cfg,
            routes_cfg={"routing_policies": [{}]},
            groups=[],
            users=[assignee_cfg],
        )
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_journal_entry_marks_sent_after_delivery() -> None:
    client = AsyncMock()
    session = AsyncMock()
    issue = _issue()
    journal = _journal()
    assignee_cfg = {"id": 1, "redmine_id": 10, "room": "!r:example", "notify": ["all"]}
    with (
        patch("bot.journal_handlers.watcher_cfgs_for_routing", new=AsyncMock(return_value=[])),
        patch(
            "bot.journal_handlers.resolve_policy_target_rooms",
            return_value=PolicyRoutingResult(
                deliveries=(("!r:example", "new"),),
                matched_policy_ids=(1,),
                action_kind="created",
            ),
        ),
        patch("bot.journal_handlers.can_notify", return_value=True),
        patch(
            "bot.journal_handlers.should_send_journal_notification",
            new=AsyncMock(return_value=True),
        ),
        patch("bot.journal_handlers.journal_render_send_or_dlq", new=AsyncMock(return_value=True)),
        patch("bot.journal_handlers.mark_journal_notification_sent", new=AsyncMock()) as mark_mock,
    ):
        await handle_journal_entry(
            client,
            session,
            issue=issue,
            journal=journal,
            assignee_cfg=assignee_cfg,
            routes_cfg={"routing_policies": [{}]},
            groups=[],
            users=[assignee_cfg],
        )
    mark_mock.assert_awaited_once()
