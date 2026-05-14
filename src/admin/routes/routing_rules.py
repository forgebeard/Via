"""Routing policy CRUD (Rules v2): только POST под /onboarding/rules*, UI — вкладка onboarding#rules."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    NotificationType,
    RedminePriority,
    RedmineStatus,
    RedmineVersion,
    RoutingPolicy,
    RoutingPolicyPriority,
    RoutingPolicyStatus,
    RoutingPolicyVersion,
)
from database.session import get_session

router = APIRouter(tags=["routing_rules"])

_ONBOARDING_RULES = "/onboarding#rules"
_ONBOARDING_RULES_WARN = "/onboarding?warn={warn}#rules"

_ALLOWED_MODES = frozenset({"match_rooms", "assignee", "watchers"})


def _admin() -> Any:
    import admin.main as _m

    return _m


def _require_admin(request: Request) -> Any:
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Только admin")
    return user


def _redirect_onboarding(*, warn: str | None = None) -> RedirectResponse:
    if warn and warn.strip():
        return RedirectResponse(
            _ONBOARDING_RULES_WARN.format(warn=quote(warn.strip(), safe="")),
            status_code=303,
        )
    return RedirectResponse(_ONBOARDING_RULES, status_code=303)


def _parse_ids(raw_values: list[str] | None) -> list[int]:
    out: list[int] = []
    for v in raw_values or []:
        s = str(v or "").strip()
        if not s:
            continue
        try:
            out.append(int(s))
        except ValueError:
            continue
    return sorted(set(out))


def _normalize_action_kind(raw_value: str) -> str:
    value = (raw_value or "").strip().lower()
    if value in {"created", "updated"}:
        return value
    raise HTTPException(status_code=400, detail="action_kind должен быть created|updated")


def _parse_recipient_modes(raw: list[str] | None) -> list[str]:
    out = [x for x in (raw or []) if x in _ALLOWED_MODES]
    return sorted(set(out)) or ["match_rooms"]


async def _notification_type_id_for_action(session: AsyncSession, action_kind: str) -> int:
    key = "new" if action_kind == "created" else "issue_updated"
    nid = await session.scalar(select(NotificationType.id).where(NotificationType.key == key))
    if nid is None:
        raise HTTPException(
            status_code=500,
            detail=f"В БД отсутствует notification_types.key={key}",
        )
    return int(nid)


async def _catalogs(
    session: AsyncSession,
) -> tuple[
    list[RedmineStatus],
    list[RedmineVersion],
    list[RedminePriority],
]:
    rs = list(
        (
            await session.execute(
                select(RedmineStatus)
                .where(RedmineStatus.is_active.is_(True))
                .order_by(RedmineStatus.name)
            )
        ).scalars()
    )
    rv = list(
        (
            await session.execute(
                select(RedmineVersion)
                .where(RedmineVersion.is_active.is_(True))
                .order_by(RedmineVersion.name)
            )
        ).scalars()
    )
    rp = list(
        (
            await session.execute(
                select(RedminePriority)
                .where(RedminePriority.is_active.is_(True))
                .order_by(RedminePriority.name)
            )
        ).scalars()
    )
    return rs, rv, rp


async def _validate_fk_active(
    session: AsyncSession, status_ids: list[int], version_ids: list[int], priority_ids: list[int]
) -> None:
    if status_ids:
        active = set(
            (
                await session.execute(
                    select(RedmineStatus.id).where(
                        and_(
                            RedmineStatus.id.in_(status_ids),
                            RedmineStatus.is_active.is_(True),
                        )
                    )
                )
            ).scalars()
        )
        if active != set(status_ids):
            raise HTTPException(
                status_code=400, detail="Некоторые status_id не существуют или неактивны"
            )
    if version_ids:
        active = set(
            (
                await session.execute(
                    select(RedmineVersion.id).where(
                        and_(
                            RedmineVersion.id.in_(version_ids),
                            RedmineVersion.is_active.is_(True),
                        )
                    )
                )
            ).scalars()
        )
        if active != set(version_ids):
            raise HTTPException(
                status_code=400, detail="Некоторые version_id не существуют или неактивны"
            )
    if priority_ids:
        active = set(
            (
                await session.execute(
                    select(RedminePriority.id).where(
                        and_(
                            RedminePriority.id.in_(priority_ids),
                            RedminePriority.is_active.is_(True),
                        )
                    )
                )
            ).scalars()
        )
        if active != set(priority_ids):
            raise HTTPException(
                status_code=400, detail="Некоторые priority_id не существуют или неактивны"
            )


async def _overlap_warning(
    session: AsyncSession, *, action_kind: str, exclude_id: int | None = None
) -> str | None:
    stmt = select(RoutingPolicy).where(RoutingPolicy.enabled.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(RoutingPolicy.id != exclude_id)
    row = (await session.execute(stmt.order_by(RoutingPolicy.id))).scalars().first()
    if row is None:
        return None
    return (
        f"Возможное пересечение с правилом #{row.id}. "
        "Поле action_kind носит вспомогательный характер, проверьте оси статуса/версии/приоритета."
    )


async def _replace_policy_links(
    session: AsyncSession,
    *,
    policy_id: int,
    status_ids: list[int],
    version_ids: list[int],
    priority_ids: list[int],
) -> None:
    await session.execute(
        delete(RoutingPolicyStatus).where(RoutingPolicyStatus.policy_id == policy_id)
    )
    await session.execute(
        delete(RoutingPolicyPriority).where(RoutingPolicyPriority.policy_id == policy_id)
    )
    await session.execute(
        delete(RoutingPolicyVersion).where(RoutingPolicyVersion.policy_id == policy_id)
    )
    for sid in status_ids:
        session.add(RoutingPolicyStatus(policy_id=policy_id, status_id=sid))
    for vid in version_ids:
        session.add(RoutingPolicyVersion(policy_id=policy_id, version_id=vid))
    for pid in priority_ids:
        session.add(RoutingPolicyPriority(policy_id=policy_id, priority_id=pid))


async def build_routing_rules_context(session: AsyncSession, warn: str = "") -> dict[str, Any]:
    policies = list(
        (await session.execute(select(RoutingPolicy).order_by(RoutingPolicy.id))).scalars()
    )
    policy_ids = [int(p.id) for p in policies]
    by_status: dict[int, list[int]] = defaultdict(list)
    by_version: dict[int, list[int]] = defaultdict(list)
    by_priority: dict[int, list[int]] = defaultdict(list)
    if policy_ids:
        for r in (
            await session.execute(
                select(RoutingPolicyStatus).where(RoutingPolicyStatus.policy_id.in_(policy_ids))
            )
        ).scalars():
            by_status[int(r.policy_id)].append(int(r.status_id))
        for r in (
            await session.execute(
                select(RoutingPolicyVersion).where(RoutingPolicyVersion.policy_id.in_(policy_ids))
            )
        ).scalars():
            by_version[int(r.policy_id)].append(int(r.version_id))
        for r in (
            await session.execute(
                select(RoutingPolicyPriority).where(RoutingPolicyPriority.policy_id.in_(policy_ids))
            )
        ).scalars():
            by_priority[int(r.policy_id)].append(int(r.priority_id))
    statuses, versions, priorities = await _catalogs(session)
    journal_rows = (
        await session.execute(
            select(NotificationType.id, NotificationType.key, NotificationType.label)
            .where(
                NotificationType.key.in_(("new", "issue_updated")),
                NotificationType.is_active.is_(True),
            )
            .order_by(NotificationType.sort_order.asc(), NotificationType.id.asc())
        )
    ).all()
    key_to_action = {"new": "created", "issue_updated": "updated"}
    journal_notification_choices: list[dict[str, Any]] = []
    for nid, key, label in journal_rows:
        ak = key_to_action.get(str(key or ""))
        if ak:
            journal_notification_choices.append(
                {
                    "id": int(nid),
                    "key": str(key),
                    "label": str(label or key),
                    "action_kind": ak,
                }
            )
    for key, label in (("new", "Новая задача"), ("issue_updated", "Задача обновлена")):
        if not any(c["key"] == key for c in journal_notification_choices):
            ak = key_to_action[key]
            journal_notification_choices.append(
                {"id": 0, "key": key, "label": label, "action_kind": ak}
            )
    journal_notification_choices.sort(
        key=lambda c: (0 if c["key"] == "new" else 1, c["label"]),
    )
    rule_recipient_modes: dict[int, list[str]] = {}
    for p in policies:
        raw = getattr(p, "recipient_modes", None)
        if isinstance(raw, list):
            rule_recipient_modes[int(p.id)] = [str(x) for x in raw if str(x) in _ALLOWED_MODES]
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    rule_recipient_modes[int(p.id)] = [
                        str(x) for x in parsed if str(x) in _ALLOWED_MODES
                    ]
            except json.JSONDecodeError:
                rule_recipient_modes[int(p.id)] = ["match_rooms"]
        if int(p.id) not in rule_recipient_modes:
            rule_recipient_modes[int(p.id)] = ["match_rooms"]
    return {
        "rules": policies,
        "statuses": statuses,
        "versions": versions,
        "priorities": priorities,
        "rule_status_ids": {k: sorted(v) for k, v in by_status.items()},
        "rule_version_ids": {k: sorted(v) for k, v in by_version.items()},
        "rule_priority_ids": {k: sorted(v) for k, v in by_priority.items()},
        "rule_recipient_modes": rule_recipient_modes,
        "journal_notification_choices": journal_notification_choices,
        "warn": (warn or "").strip(),
    }


@router.get("/settings/routing-rules", response_class=HTMLResponse)
async def routing_rules_legacy_redirect():
    return RedirectResponse(_ONBOARDING_RULES, status_code=307)


@router.post("/onboarding/rules")
async def onboarding_rules_create(
    request: Request,
    name: Annotated[str, Form()] = "",
    action_kind: Annotated[str, Form()] = "updated",
    status_ids: Annotated[list[str], Form()] = [],
    version_ids: Annotated[list[str], Form()] = [],
    priority_ids: Annotated[list[str], Form()] = [],
    recipient_modes: Annotated[list[str], Form()] = [],
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    user = _require_admin(request)
    admin._verify_csrf(request, csrf_token)
    action_kind_norm = _normalize_action_kind(action_kind)
    status_ids_i = _parse_ids(status_ids)
    version_ids_i = _parse_ids(version_ids)
    priority_ids_i = _parse_ids(priority_ids)
    modes = _parse_recipient_modes(recipient_modes)
    await _validate_fk_active(session, status_ids_i, version_ids_i, priority_ids_i)
    nt_id = await _notification_type_id_for_action(session, action_kind_norm)
    row = RoutingPolicy(
        name=(name or "").strip() or "policy",
        enabled=True,
        action_kind=action_kind_norm,
        notification_type_id=nt_id,
        recipient_modes=modes,
    )
    session.add(row)
    await session.flush()
    row.enabled = True
    await _replace_policy_links(
        session,
        policy_id=int(row.id),
        status_ids=status_ids_i,
        version_ids=version_ids_i,
        priority_ids=priority_ids_i,
    )
    await admin._maybe_log_admin_crud(
        session,
        user,
        "routing_policy",
        "create",
        {
            "id": row.id,
            "action_kind": row.action_kind,
            "notification_type_id": nt_id,
            "recipient_modes": modes,
            "status_ids": status_ids_i,
            "version_ids": version_ids_i,
            "priority_ids": priority_ids_i,
        },
    )
    warning = await _overlap_warning(
        session,
        action_kind=str(row.action_kind),
        exclude_id=row.id,
    )
    if not status_ids_i and not version_ids_i and not priority_ids_i:
        warning = (
            warning + " " if warning else ""
        ) + "Правило без условий применится ко всем задачам. Вы уверены?"
    return _redirect_onboarding(warn=warning)


@router.post("/onboarding/rules/{rule_id}")
async def onboarding_rules_update(
    request: Request,
    rule_id: int,
    name: Annotated[str, Form()] = "",
    action_kind: Annotated[str, Form()] = "updated",
    status_ids: Annotated[list[str], Form()] = [],
    version_ids: Annotated[list[str], Form()] = [],
    priority_ids: Annotated[list[str], Form()] = [],
    recipient_modes: Annotated[list[str], Form()] = [],
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    user = _require_admin(request)
    admin._verify_csrf(request, csrf_token)
    row = await session.get(RoutingPolicy, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Policy не найден")
    action_kind_norm = _normalize_action_kind(action_kind)
    status_ids_i = _parse_ids(status_ids)
    version_ids_i = _parse_ids(version_ids)
    priority_ids_i = _parse_ids(priority_ids)
    modes = _parse_recipient_modes(recipient_modes)
    await _validate_fk_active(session, status_ids_i, version_ids_i, priority_ids_i)
    nt_id = await _notification_type_id_for_action(session, action_kind_norm)
    row.name = (name or "").strip() or row.name
    row.enabled = True
    row.action_kind = action_kind_norm
    row.notification_type_id = nt_id
    row.recipient_modes = modes
    await _replace_policy_links(
        session,
        policy_id=int(row.id),
        status_ids=status_ids_i,
        version_ids=version_ids_i,
        priority_ids=priority_ids_i,
    )
    await admin._maybe_log_admin_crud(
        session,
        user,
        "routing_policy",
        "update",
        {
            "id": row.id,
            "action_kind": row.action_kind,
            "notification_type_id": nt_id,
            "recipient_modes": modes,
            "status_ids": status_ids_i,
            "version_ids": version_ids_i,
            "priority_ids": priority_ids_i,
            "enabled": row.enabled,
        },
    )
    warning = await _overlap_warning(
        session,
        action_kind=str(row.action_kind),
        exclude_id=row.id,
    )
    if not status_ids_i and not version_ids_i and not priority_ids_i:
        warning = (
            warning + " " if warning else ""
        ) + "Правило без условий применится ко всем задачам. Вы уверены?"
    return _redirect_onboarding(warn=warning)


@router.post("/onboarding/rules/{rule_id}/delete")
async def onboarding_rules_delete(
    request: Request,
    rule_id: int,
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    user = _require_admin(request)
    admin._verify_csrf(request, csrf_token)
    old = await session.get(RoutingPolicy, rule_id)
    await session.execute(delete(RoutingPolicy).where(RoutingPolicy.id == rule_id))
    await admin._maybe_log_admin_crud(
        session,
        user,
        "routing_policy",
        "delete",
        {"id": rule_id, "name": getattr(old, "name", "")},
    )
    return _redirect_onboarding()
