from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.dedup_repo import mark_journal_notification_sent, should_send_journal_notification


def _issue(*, issue_id=100, status_id=1, version_id=2, priority_id=3):
    return SimpleNamespace(
        id=issue_id,
        status=SimpleNamespace(id=status_id),
        fixed_version=SimpleNamespace(id=version_id) if version_id is not None else None,
        priority=SimpleNamespace(id=priority_id),
    )


@pytest.mark.asyncio
async def test_should_send_when_state_absent() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    assert (
        await should_send_journal_notification(
            session, issue=_issue(), room_id="!r:example", notification_type="issue_updated"
        )
        is True
    )


@pytest.mark.asyncio
async def test_should_skip_when_axes_same() -> None:
    session = AsyncMock()
    row = SimpleNamespace(status_id=1, version_id=2, priority_id=3)
    session.scalar = AsyncMock(return_value=row)
    assert (
        await should_send_journal_notification(
            session, issue=_issue(), room_id="!r:example", notification_type="new"
        )
        is False
    )


@pytest.mark.asyncio
async def test_should_send_when_axes_changed() -> None:
    session = AsyncMock()
    row = SimpleNamespace(status_id=1, version_id=2, priority_id=3)
    session.scalar = AsyncMock(return_value=row)
    assert (
        await should_send_journal_notification(
            session,
            issue=_issue(status_id=5, version_id=2, priority_id=3),
            room_id="!r:example",
            notification_type="new",
        )
        is True
    )


@pytest.mark.asyncio
async def test_mark_sent_executes_upsert() -> None:
    session = AsyncMock()
    await mark_journal_notification_sent(
        session,
        issue=_issue(issue_id=77, status_id=4, version_id=9, priority_id=2),
        room_id="!room:example",
        notification_type="issue_updated",
    )
    session.execute.assert_awaited()
