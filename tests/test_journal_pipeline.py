from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.journal_pipeline as jp


def _attach_caplog(caplog):
    lg = logging.getLogger("redmine_bot")
    lg.addHandler(caplog.handler)
    return lg


def _issue(issue_id: int, *, missing_required: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=issue_id,
        subject=f"Issue {issue_id}",
        project=SimpleNamespace(name="Project"),
        status=None if missing_required else SimpleNamespace(name="Новая"),
        priority=SimpleNamespace(name="Нормальный"),
        fixed_version=None,
        assigned_to=None,
        updated_on=datetime.now(UTC),
    )


class _IssueApi:
    def __init__(self, issues):
        self._issues = issues

    def filter(self, **_kwargs):
        return self._issues


class _Redmine:
    def __init__(self, issues):
        self.issue = _IssueApi(issues)


@pytest.mark.asyncio
async def test_contract_check_first_tick_logs_summary_for_optional(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG, logger="redmine_bot")
    jp._CONTRACT_LOGGED_ISSUES.clear()
    jp._CONTRACT_TICK_NO = 0

    async def _fake_cycle_str(_session, _key, default=""):
        return default

    async def _fake_contract_settings(_session):
        return False, 2

    async def _fake_run_in_thread(fn):
        return fn()

    async def _narrow(_session):
        return "narrow"

    async def _no_projects(_session):
        return []

    monkeypatch.setattr(jp, "_cycle_str", _fake_cycle_str)
    monkeypatch.setattr(jp, "_contract_audit_settings", _fake_contract_settings)
    monkeypatch.setattr(jp, "run_in_thread", _fake_run_in_thread)
    monkeypatch.setattr(jp, "journal_scope_mode", _narrow)
    monkeypatch.setattr(jp, "journal_project_ids", _no_projects)
    lg = _attach_caplog(caplog)

    redmine = _Redmine([_issue(1), _issue(2), _issue(3)])
    in_scope, _ = await jp.phase_a_candidates(
        redmine,
        session=AsyncMock(),
        max_issues=100,
        max_pages=1,
    )
    lg.removeHandler(caplog.handler)

    assert len(in_scope) == 3
    assert {int(x.id) for x in in_scope} == {1, 2, 3}
    text = caplog.text
    assert "journal_contract_check_summary" in text
    assert "optional_issues=3" in text
    assert "journal_contract_check issue_id=" not in text


@pytest.mark.asyncio
async def test_contract_check_required_stays_visible(caplog, monkeypatch):
    jp._CONTRACT_LOGGED_ISSUES.clear()
    jp._CONTRACT_TICK_NO = 0

    async def _fake_cycle_str(_session, _key, default=""):
        return default

    async def _fake_contract_settings(_session):
        return False, 5

    async def _fake_run_in_thread(fn):
        return fn()

    async def _narrow(_session):
        return "narrow"

    async def _no_projects(_session):
        return []

    monkeypatch.setattr(jp, "_cycle_str", _fake_cycle_str)
    monkeypatch.setattr(jp, "_contract_audit_settings", _fake_contract_settings)
    monkeypatch.setattr(jp, "run_in_thread", _fake_run_in_thread)
    monkeypatch.setattr(jp, "journal_scope_mode", _narrow)
    monkeypatch.setattr(jp, "journal_project_ids", _no_projects)
    lg = _attach_caplog(caplog)

    redmine = _Redmine([_issue(7, missing_required=True)])
    await jp.phase_a_candidates(
        redmine,
        session=AsyncMock(),
        max_issues=100,
        max_pages=1,
    )
    lg.removeHandler(caplog.handler)

    assert "journal_contract_check_required issue_id=7" in caplog.text


@pytest.mark.asyncio
async def test_contract_check_verbose_keeps_detailed_info(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="redmine_bot")
    jp._CONTRACT_LOGGED_ISSUES.clear()
    jp._CONTRACT_TICK_NO = 0

    async def _fake_cycle_str(_session, _key, default=""):
        return default

    async def _fake_contract_settings(_session):
        return True, 10

    async def _fake_run_in_thread(fn):
        return fn()

    async def _narrow(_session):
        return "narrow"

    async def _no_projects(_session):
        return []

    monkeypatch.setattr(jp, "_cycle_str", _fake_cycle_str)
    monkeypatch.setattr(jp, "_contract_audit_settings", _fake_contract_settings)
    monkeypatch.setattr(jp, "run_in_thread", _fake_run_in_thread)
    monkeypatch.setattr(jp, "journal_scope_mode", _narrow)
    monkeypatch.setattr(jp, "journal_project_ids", _no_projects)
    lg = _attach_caplog(caplog)

    redmine = _Redmine([_issue(11)])
    await jp.phase_a_candidates(
        redmine,
        session=AsyncMock(),
        max_issues=100,
        max_pages=1,
    )
    lg.removeHandler(caplog.handler)

    assert "journal_contract_check issue_id=11" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_value", ["all", "narrow"])
async def test_phase_a_scope_includes_without_bot_assignee(scope_value, monkeypatch):
    """ narrow и all: задача в scope без исполнителя из bot_users и без watcher cache."""
    jp._CONTRACT_LOGGED_ISSUES.clear()
    jp._CONTRACT_TICK_NO = 0

    async def _fake_cycle_str(_session, _key, default=""):
        return default

    async def _fake_contract_settings(_session):
        return False, 10

    async def _fake_run_in_thread(fn):
        return fn()

    async def _scope(_session):
        return scope_value

    async def _proj_empty(_session):
        return []

    monkeypatch.setattr(jp, "_cycle_str", _fake_cycle_str)
    monkeypatch.setattr(jp, "_contract_audit_settings", _fake_contract_settings)
    monkeypatch.setattr(jp, "run_in_thread", _fake_run_in_thread)
    monkeypatch.setattr(jp, "journal_scope_mode", _scope)
    monkeypatch.setattr(jp, "journal_project_ids", _proj_empty)

    issue = _issue(99)
    redmine = _Redmine([issue])
    in_scope, _ = await jp.phase_a_candidates(
        redmine,
        session=AsyncMock(),
        max_issues=100,
        max_pages=1,
    )
    assert len(in_scope) == 1
    assert int(in_scope[0].id) == 99
