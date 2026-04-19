"""Маршрутизация Matrix-комнаты для группового потока журнала.

Без HTTP/БД: только issue + конфиг из БД (через fetch_runtime_config / ROUTING).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.logic import _LEGACY_VERSION_FALLBACK_KEY, get_version_name


@dataclass(frozen=True)
class MatchedRoute:
    room_id: str
    priority: int
    sort_order: int
    notify_on_assignment: bool
    source_table: str
    source_id: int | None


def _issue_status_name_lc(issue: Any) -> str:
    try:
        return str(issue.status.name).strip().lower()
    except Exception:
        return ""


def _version_key_matches_route(version_name_lc: str, route_key_lc: str) -> bool:
    rk = (route_key_lc or "").strip().lower()
    if not rk:
        return False
    vn = (version_name_lc or "").strip().lower()
    if vn:
        return rk in vn
    return rk == _LEGACY_VERSION_FALLBACK_KEY.strip().lower()


def _status_key_matches_route(status_name_lc: str, route_key_lc: str) -> bool:
    sk = (route_key_lc or "").strip().lower()
    if not sk:
        return False
    st = (status_name_lc or "").strip().lower()
    if not st:
        return False
    return sk in st or st in sk


def get_matching_route(
    issue: Any,
    routes_config: dict[str, Any] | None,
    assignee_cfg: dict[str, Any],
    *,
    groups: list[dict[str, Any]] | None = None,
) -> MatchedRoute | None:
    """
    Возвращает один лучший маршрут для групповой комнаты по задаче и исполнителю.

    Порядок перебора (при равенстве priority/sort_order — порядок появления в конфиге):
    персональные и групповые version_routes в ``assignee_cfg['version_routes']``,
    глобальные ``version_routes_global``, ``status_routes``, затем комната support_group исполнителя.
    """
    routes_config = routes_config or {}
    groups = groups or []

    version_name_lc = (get_version_name(issue) or "").lower()
    status_name_lc = _issue_status_name_lc(issue)

    scored: list[tuple[tuple[int, int, int], MatchedRoute]] = []
    seq = 0

    for spec in assignee_cfg.get("version_routes") or []:
        key = (spec.get("key") or "").strip()
        rid = (spec.get("room") or "").strip()
        if not key or not rid:
            continue
        if not _version_key_matches_route(version_name_lc, key.lower()):
            continue
        src = str(spec.get("route_source") or "user_version_route")
        rid_sql = spec.get("route_id")
        scored.append(
            (
                (int(spec.get("priority", 100)), int(spec.get("sort_order", 0)), seq),
                MatchedRoute(
                    room_id=rid,
                    priority=int(spec.get("priority", 100)),
                    sort_order=int(spec.get("sort_order", 0)),
                    notify_on_assignment=bool(spec.get("notify_on_assignment", True)),
                    source_table=src,
                    source_id=int(rid_sql) if rid_sql is not None else None,
                ),
            )
        )
        seq += 1

    for spec in routes_config.get("version_routes_global") or []:
        key = (spec.get("version_key") or "").strip()
        rid = (spec.get("room_id") or "").strip()
        if not key or not rid:
            continue
        if not _version_key_matches_route(version_name_lc, key.lower()):
            continue
        rid_sql = spec.get("route_id")
        scored.append(
            (
                (int(spec.get("priority", 100)), int(spec.get("sort_order", 0)), seq),
                MatchedRoute(
                    room_id=rid,
                    priority=int(spec.get("priority", 100)),
                    sort_order=int(spec.get("sort_order", 0)),
                    notify_on_assignment=bool(spec.get("notify_on_assignment", True)),
                    source_table=str(spec.get("route_source") or "version_room_route"),
                    source_id=int(rid_sql) if rid_sql is not None else None,
                ),
            )
        )
        seq += 1

    for spec in routes_config.get("status_routes") or []:
        key = (spec.get("status_key") or "").strip()
        rid = (spec.get("room_id") or "").strip()
        if not key or not rid:
            continue
        if not _status_key_matches_route(status_name_lc, key.lower()):
            continue
        rid_sql = spec.get("route_id")
        scored.append(
            (
                (int(spec.get("priority", 100)), int(spec.get("sort_order", 0)), seq),
                MatchedRoute(
                    room_id=rid,
                    priority=int(spec.get("priority", 100)),
                    sort_order=int(spec.get("sort_order", 0)),
                    notify_on_assignment=bool(spec.get("notify_on_assignment", True)),
                    source_table=str(spec.get("route_source") or "status_room_route"),
                    source_id=int(rid_sql) if rid_sql is not None else None,
                ),
            )
        )
        seq += 1

    gid = assignee_cfg.get("group_id")
    if gid is not None:
        for g in groups:
            if int(g.get("group_id", -1)) != int(gid):
                continue
            room = (g.get("room") or "").strip()
            if not room:
                continue
            scored.append(
                (
                    (10_000, 0, seq),
                    MatchedRoute(
                        room_id=room,
                        priority=10_000,
                        sort_order=0,
                        notify_on_assignment=bool(g.get("notify_on_assignment", True)),
                        source_table="support_groups",
                        source_id=int(gid),
                    ),
                )
            )
            seq += 1
            break

    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]
