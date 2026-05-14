"""
Загрузка runtime-конфига из Postgres для policy-based маршрутизации.

См. docs/ROUTING_POLICIES.md
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    BotUser,
    CycleSettings,
    NotificationType,
    RoutingPolicy,
    RoutingPolicyPriority,
    RoutingPolicyStatus,
    RoutingPolicyVersion,
    SupportGroup,
)
from .session import get_session_factory

logger = logging.getLogger("redmine_bot")


def user_orm_to_cfg(
    row: BotUser,
    groups_by_id: dict[int, SupportGroup],
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": row.id,
        "redmine_id": row.redmine_id,
        "room": row.room,
        "notify": row.notify if isinstance(row.notify, list) else ["all"],
        "versions": row.versions if isinstance(row.versions, list) else ["all"],
        "priorities": row.priorities if isinstance(row.priorities, list) else ["all"],
    }
    if row.group_id is not None:
        d["group_id"] = row.group_id
        g = groups_by_id.get(row.group_id)
        if g is not None:
            d["group_name"] = g.name
            d["group_room"] = g.room_id
            d["group_notify_on_assignment"] = bool(getattr(g, "notify_on_assignment", True))
            if g.timezone:
                d["group_timezone"] = g.timezone
            d["group_delivery"] = {
                "notify": g.notify if isinstance(g.notify, list) else ["all"],
                "versions": g.versions if isinstance(g.versions, list) else ["all"],
                "priorities": g.priorities if isinstance(g.priorities, list) else ["all"],
                "work_hours": g.work_hours,
                "work_days": g.work_days,
                "dnd": bool(g.dnd),
            }
    if row.timezone:
        d["timezone"] = row.timezone
    if row.work_hours:
        d["work_hours"] = row.work_hours
    if row.work_days is not None:
        d["work_days"] = row.work_days
    if row.dnd:
        d["dnd"] = True
    ciph = getattr(row, "redmine_api_key_ciphertext", None)
    nonce = getattr(row, "redmine_api_key_nonce", None)
    if ciph and nonce:
        d["_redmine_key_cipher"] = ciph
        d["_redmine_key_nonce"] = nonce
    return d


def group_orm_to_cfg(row: SupportGroup) -> dict[str, Any]:
    out: dict[str, Any] = {
        "group_id": row.id,
        "group_name": row.name,
        "room": row.room_id,
        "notify_on_assignment": bool(getattr(row, "notify_on_assignment", True)),
        "notify": row.notify if isinstance(row.notify, list) else ["all"],
        "versions": row.versions if isinstance(row.versions, list) else ["all"],
        "priorities": row.priorities if isinstance(row.priorities, list) else ["all"],
        "work_hours": row.work_hours,
        "work_days": row.work_days,
        "dnd": bool(row.dnd),
    }
    if row.timezone:
        out["timezone"] = row.timezone
    return out


async def fetch_runtime_config(
    session: AsyncSession | None = None,
) -> tuple[list, list, dict[str, Any]]:
    """
    Возвращает (USERS, GROUPS, routes_config).

    Legacy-плоские мапы статус/версия→комната убраны: маршрутизация только через
    ``routes_config["routing_policies"]``.
    """
    if session is None:
        factory = get_session_factory()
        async with factory() as s:
            return await fetch_runtime_config(s)

    r_groups = await session.execute(select(SupportGroup).order_by(SupportGroup.id))
    groups = list(r_groups.scalars().all())
    groups_by_id = {g.id: g for g in groups}

    r_users = await session.execute(select(BotUser).order_by(BotUser.redmine_id))
    users = [user_orm_to_cfg(u, groups_by_id) for u in r_users.scalars().all()]
    groups_cfg = [group_orm_to_cfg(g) for g in groups]

    routes_config: dict[str, Any] = {
        "status_routes": [],
        "version_routes_global": [],
        "routing_policies": [],
    }

    policies = list(
        (
            await session.execute(
                select(RoutingPolicy)
                .where(RoutingPolicy.enabled.is_(True))
                .order_by(RoutingPolicy.id)
            )
        ).scalars()
    )
    policy_ids = [int(p.id) for p in policies]
    nt_ids = {int(p.notification_type_id) for p in policies}
    id_to_nt_key: dict[int, str] = {}
    if nt_ids:
        r_nt = await session.execute(
            select(NotificationType).where(NotificationType.id.in_(nt_ids))
        )
        for nt in r_nt.scalars().all():
            id_to_nt_key[int(nt.id)] = str(nt.key or "")
    status_map_by_policy: dict[int, list[int]] = defaultdict(list)
    priority_map_by_policy: dict[int, list[int]] = defaultdict(list)
    version_map_by_policy: dict[int, list[int]] = defaultdict(list)
    if policy_ids:
        for status_row in (
            await session.execute(
                select(RoutingPolicyStatus).where(RoutingPolicyStatus.policy_id.in_(policy_ids))
            )
        ).scalars():
            status_map_by_policy[int(status_row.policy_id)].append(int(status_row.status_id))
        for priority_row in (
            await session.execute(
                select(RoutingPolicyPriority).where(RoutingPolicyPriority.policy_id.in_(policy_ids))
            )
        ).scalars():
            priority_map_by_policy[int(priority_row.policy_id)].append(
                int(priority_row.priority_id)
            )
        for version_row in (
            await session.execute(
                select(RoutingPolicyVersion).where(RoutingPolicyVersion.policy_id.in_(policy_ids))
            )
        ).scalars():
            version_map_by_policy[int(version_row.policy_id)].append(int(version_row.version_id))
    routes_config["routing_policies"] = [
        {
            "id": int(p.id),
            "name": str(p.name or ""),
            "enabled": bool(p.enabled),
            "action_kind": str(getattr(p, "action_kind", "") or "updated"),
            "notification_type_key": id_to_nt_key.get(int(p.notification_type_id), "issue_updated"),
            "recipient_modes": list(p.recipient_modes)
            if isinstance(getattr(p, "recipient_modes", None), list)
            else ["match_rooms"],
            "status_ids": sorted(status_map_by_policy.get(int(p.id), [])),
            "priority_ids": sorted(priority_map_by_policy.get(int(p.id), [])),
            "version_ids": sorted(version_map_by_policy.get(int(p.id), [])),
        }
        for p in policies
    ]

    return users, groups_cfg, routes_config


async def fetch_cycle_settings(session: AsyncSession | None = None) -> dict[str, str]:
    """
    Загружает настройки цикла из таблицы cycle_settings.
    Возвращает {key: value} — например {"CHECK_INTERVAL": "90"}.
    """
    if session is None:
        factory = get_session_factory()
        async with factory() as s:
            return await fetch_cycle_settings(s)

    result = await session.execute(select(CycleSettings))
    return {row.key: row.value for row in result.scalars().all()}
