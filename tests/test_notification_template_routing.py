"""Маппинг типов уведомлений на tpl и tpl-ветка build_matrix_message_content."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import matrix_send
from bot.catalogs import BotCatalogs
from bot.logic import NOTIFICATION_TYPES
from bot.notification_template_routing import (
    EVENT_TO_TEMPLATE,
    assert_event_map_covers_notification_types,
)

# Как в test_bot.TestSendSafe: круглосуточно, все дни — send_safe не режет по DND.
_USER_CFG_FOR_SEND = {
    "redmine_id": 1,
    "room": "!room:server",
    "notify": ["all"],
    "work_hours": "00:00-23:59",
    "work_days": [0, 1, 2, 3, 4, 5, 6],
}


def test_event_to_template_covers_notification_types() -> None:
    assert_event_map_covers_notification_types()
    assert EVENT_TO_TEMPLATE["new"] == "tpl_new_issue"
    assert EVENT_TO_TEMPLATE["status_change"] == "tpl_task_change"
    assert EVENT_TO_TEMPLATE["reminder"] == "tpl_reminder"


@pytest.mark.asyncio
async def test_build_matrix_requires_session_when_tpl_mode(simple_issue):
    from bot import sender

    with pytest.raises(RuntimeError, match="AsyncSession required"):
        await sender.build_matrix_message_content(simple_issue, "new", session=None)


@pytest.mark.asyncio
async def test_build_matrix_tpl_path_uses_render_named_template(simple_issue):
    import bot.config_state as config_state
    from bot import sender

    config_state.CATALOGS = BotCatalogs(
        status_id_to_name={1: "Новая"},
        priority_id_to_name={2: "Normal"},
    )
    mock_session = AsyncMock()

    async def _fake_render(session, name, context, *, root=None):
        assert name == "tpl_new_issue"
        assert context["issue_id"] == simple_issue.id
        return "<p>tpl-test</p>", "plain tpl-test"

    with patch("bot.template_loader.render_named_template", new=_fake_render):
        out = await sender.build_matrix_message_content(
            simple_issue, "new", session=mock_session
        )
    assert out["formatted_body"] == "<p>tpl-test</p>"
    assert out["body"] == "plain tpl-test"
    assert out["msgtype"] == "m.text"


@pytest.mark.parametrize("event_type", sorted(EVENT_TO_TEMPLATE.keys()))
@pytest.mark.asyncio
async def test_build_matrix_tpl_event_map_parametrized(simple_issue, event_type: str) -> None:
    """Для каждого ключа EVENT_TO_TEMPLATE — ожидаемое tpl_* и issue_id в контексте."""
    import bot.config_state as config_state
    from bot import sender

    config_state.CATALOGS = BotCatalogs(
        status_id_to_name={1: "Новая"},
        priority_id_to_name={2: "Normal"},
    )
    mock_session = AsyncMock()
    captured: dict[str, object] = {}

    async def _fake_render(session, name, context, *, root=None):
        captured["name"] = name
        captured["context"] = dict(context)
        return "<p>ok</p>", "plain ok"

    with patch("bot.template_loader.render_named_template", new=_fake_render):
        await sender.build_matrix_message_content(
            simple_issue,
            event_type,
            extra_text="pytest extra",
            session=mock_session,
        )

    assert captured["name"] == EVENT_TO_TEMPLATE[event_type]
    ctx = captured["context"]
    assert isinstance(ctx, dict)
    assert ctx["issue_id"] == simple_issue.id
    if event_type == "reminder":
        assert ctx.get("reminder_text") == "Задача без движения"
        assert ctx.get("title") == "Напоминание"
    else:
        assert ctx.get("event_type") == NOTIFICATION_TYPES[event_type][1]
        assert "pytest extra" in (ctx.get("extra_text") or "")


@pytest.mark.asyncio
async def test_send_safe_dlq_uses_tpl_payload(simple_issue) -> None:
    """При падении Matrix send_safe кладёт в DLQ payload из build_matrix_message_content (tpl + session)."""
    import bot.config_state as config_state
    from bot import sender

    config_state.CATALOGS = BotCatalogs(
        status_id_to_name={1: "Новая"},
        priority_id_to_name={2: "Normal"},
    )
    mock_session = AsyncMock()
    enqueued: list[dict] = []

    async def _fake_render(session, name, context, *, root=None):
        assert name == EVENT_TO_TEMPLATE["info"]
        return "<p>dlq-body</p>", "plain dlq"

    async def _capture_enqueue(session, **kwargs):
        enqueued.append(kwargs)

    client = AsyncMock()
    client.room_send = AsyncMock(side_effect=RuntimeError("matrix unavailable"))

    with (
        patch("bot.template_loader.render_named_template", new=_fake_render),
        patch("database.dlq_repo.enqueue_notification", new=_capture_enqueue),
        patch("matrix_send.asyncio.sleep", new_callable=AsyncMock),
    ):
        await sender.send_safe(
            client,
            simple_issue,
            _USER_CFG_FOR_SEND,
            "!room:server",
            "info",
            extra_text="err ctx",
            db_session=mock_session,
        )

    assert len(enqueued) == 1
    row = enqueued[0]
    assert row["notification_type"] == "info"
    assert row["issue_id"] == simple_issue.id
    assert row["room_id"] == "!room:server"
    assert row["user_redmine_id"] == 1
    assert "matrix unavailable" in row["error"]
    assert row["payload"]["formatted_body"] == "<p>dlq-body</p>"
    assert row["payload"]["body"] == "plain dlq"
    assert client.room_send.call_count == matrix_send.MAX_RETRIES
