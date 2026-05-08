"""Rules-only маршрутизация Matrix-комнаты для группового потока."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bot.logic import issue_matches_cfg, should_notify

logger = logging.getLogger("redmine_bot")

_ALLOWED_RECIPIENT_MODES = frozenset({"match_rooms", "assignee", "watchers"})


@dataclass(frozen=True)
class MatchedRoute:
    room_id: str
    priority: int
    sort_order: int
    notify_on_assignment: bool
    source_table: str
    source_id: int | None


@dataclass(frozen=True)
class PolicyRoutingResult:
    """(room_id, notification_type_key) пары; room_ids — для legacy-сравнений."""

    deliveries: tuple[tuple[str, str], ...]
    matched_policy_ids: tuple[int, ...]
    action_kind: str

    @property
    def room_ids(self) -> list[str]:
        return sorted({r for r, _ in self.deliveries})


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _issue_axis_ids(issue: Any) -> tuple[int | None, int | None, int | None]:
    status_id = _int_or_none(getattr(getattr(issue, "status", None), "id", None))
    priority_id = _int_or_none(getattr(getattr(issue, "priority", None), "id", None))
    version_obj = getattr(issue, "fixed_version", None) or getattr(issue, "target_version", None)
    version_id = _int_or_none(getattr(version_obj, "id", None))
    return status_id, version_id, priority_id


def _rule_matches_axis(rule_value: int | None, issue_value: int | None) -> bool:
    if rule_value is None:
        return True
    if issue_value is None:
        return False
    return int(rule_value) == int(issue_value)


def _axis_matches(values: list[int], issue_value: int | None) -> bool:
    if not values:
        return True
    if issue_value is None:
        return False
    return int(issue_value) in {int(v) for v in values}


def _notify_token_for_action(action_kind: str) -> str:
    """Сопоставление action_kind -> ключ подписки notify для обратной совместимости."""
    kind = (action_kind or "").strip().lower()
    if kind == "created":
        return "new"
    return "issue_updated"


def _normalize_recipient_modes(raw: Any) -> list[str]:
    if raw is None:
        return ["match_rooms"]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            raw = parsed
        except (json.JSONDecodeError, TypeError):
            return ["match_rooms"]
    if not isinstance(raw, list):
        return ["match_rooms"]
    out = [str(x).strip() for x in raw if str(x).strip() in _ALLOWED_RECIPIENT_MODES]
    return out or ["match_rooms"]


def _notification_type_key_for_policy(p: dict[str, Any], action: str) -> str:
    key = str(p.get("notification_type_key") or "").strip()
    if key in ("new", "issue_updated"):
        return key
    return _notify_token_for_action(action)


def _dedupe_deliveries(pairs: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for room_id, nkey in pairs:
        rid = (room_id.strip(), nkey)
        if rid in seen:
            continue
        seen.add(rid)
        out.append((room_id.strip(), nkey))
    return tuple(out)


def resolve_policy_target_rooms(
    issue: Any,
    routes_config: dict[str, Any] | None,
    *,
    action_kind: str,
    users: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    actor_redmine_id: int | None = None,
    log_prefix: str = "routing_policy",
    assignee_cfg: dict[str, Any] | None = None,
    watcher_cfgs: list[dict[str, Any]] | None = None,
) -> PolicyRoutingResult:
    users = users or []
    groups = groups or []
    watcher_cfgs = watcher_cfgs or []
    routes_config = routes_config or {}
    status_id, version_id, priority_id = _issue_axis_ids(issue)
    action = str(action_kind or "").strip().lower()
    policies = list(routes_config.get("routing_policies") or [])
    matched_policies: list[dict[str, Any]] = []
    for p in policies:
        p_action = str(p.get("action_kind") or "").strip().lower()
        if p_action != action:
            continue
        status_values = [_int_or_none(x) for x in (p.get("status_ids") or [])]
        if not _axis_matches([int(x) for x in status_values if x is not None], status_id):
            continue
        priority_values = [_int_or_none(x) for x in (p.get("priority_ids") or [])]
        if not _axis_matches([int(x) for x in priority_values if x is not None], priority_id):
            continue
        version_values = [_int_or_none(x) for x in (p.get("version_ids") or [])]
        if not _axis_matches([int(x) for x in version_values if x is not None], version_id):
            continue
        matched_policies.append(p)
    if not matched_policies:
        payload_no_match: dict[str, Any] = {
            "event": "routing_no_match",
            "engine": "policy_v4",
            "action_kind": action,
            "issue_id": _int_or_none(getattr(issue, "id", None)),
            "status_id": status_id,
            "version_id": version_id,
            "priority_id": priority_id,
            "matched_policy_count": 0,
            "ts": datetime.now(UTC).isoformat(),
        }
        logger.warning(json.dumps(payload_no_match, ensure_ascii=False))
        return PolicyRoutingResult(deliveries=(), matched_policy_ids=(), action_kind=action)

    deliveries_acc: list[tuple[str, str]] = []
    matched_policy_ids: list[int] = []
    for p in matched_policies:
        pid = _int_or_none(p.get("id"))
        if pid is not None:
            matched_policy_ids.append(pid)
        notify_key = _notification_type_key_for_policy(p, action)
        modes = _normalize_recipient_modes(p.get("recipient_modes"))

        if "match_rooms" in modes:
            for cfg in users:
                room = str(cfg.get("room") or "").strip()
                if not room:
                    continue
                recipient_rid = _int_or_none(cfg.get("redmine_id"))
                if action == "updated" and actor_redmine_id and recipient_rid == int(
                    actor_redmine_id
                ):
                    continue
                if not should_notify(cfg, notify_key):
                    continue
                if not issue_matches_cfg(issue, cfg):
                    continue
                deliveries_acc.append((room, notify_key))
            for gcfg in groups:
                room = str(gcfg.get("room") or "").strip()
                if not room:
                    continue
                if not should_notify(gcfg, notify_key):
                    continue
                if not issue_matches_cfg(issue, gcfg):
                    continue
                deliveries_acc.append((room, notify_key))

        if "assignee" in modes and assignee_cfg:
            room = str(assignee_cfg.get("room") or "").strip()
            if room and issue_matches_cfg(issue, assignee_cfg) and should_notify(
                assignee_cfg, notify_key
            ):
                ar = _int_or_none(assignee_cfg.get("redmine_id"))
                if not (action == "updated" and actor_redmine_id and ar == int(actor_redmine_id)):
                    deliveries_acc.append((room, notify_key))

        if "watchers" in modes:
            for wcfg in watcher_cfgs:
                room = str(wcfg.get("room") or "").strip()
                if not room:
                    continue
                wr = _int_or_none(wcfg.get("redmine_id"))
                if action == "updated" and actor_redmine_id and wr == int(actor_redmine_id):
                    continue
                if not should_notify(wcfg, notify_key):
                    continue
                if not issue_matches_cfg(issue, wcfg):
                    continue
                deliveries_acc.append((room, notify_key))

    deduped = _dedupe_deliveries(deliveries_acc)
    if not deduped:
        payload_empty: dict[str, Any] = {
            "event": "routing_empty_target",
            "engine": "policy_v4",
            "action_kind": action,
            "issue_id": _int_or_none(getattr(issue, "id", None)),
            "matched_policy_ids": matched_policy_ids,
            "ts": datetime.now(UTC).isoformat(),
        }
        logger.warning(json.dumps(payload_empty, ensure_ascii=False))
    else:
        payload_match: dict[str, Any] = {
            "event": f"{log_prefix}_match",
            "engine": "policy_v4",
            "action_kind": action,
            "issue_id": _int_or_none(getattr(issue, "id", None)),
            "matched_policy_ids": matched_policy_ids,
            "target_rooms_count": len(deduped),
            "target_rooms": [d[0] for d in deduped],
            "ts": datetime.now(UTC).isoformat(),
        }
        logger.info(json.dumps(payload_match, ensure_ascii=False))
    return PolicyRoutingResult(
        deliveries=deduped,
        matched_policy_ids=tuple(matched_policy_ids),
        action_kind=action,
    )


def get_matching_route(
    issue: Any,
    routes_config: dict[str, Any] | None,
    assignee_cfg: dict[str, Any],
    *,
    groups: list[dict[str, Any]] | None = None,
) -> MatchedRoute | None:
    """Возвращает лучший маршрут только из notification_routing_rules."""
    routes_config = routes_config or {}
    status_id, version_id, priority_id = _issue_axis_ids(issue)
    rules = list(routes_config.get("routing_rules") or [])
    candidates: list[tuple[tuple[int, int, int], MatchedRoute]] = []
    for spec in rules:
        room_id = (spec.get("target_room_id") or "").strip()
        if not room_id:
            continue
        if not _rule_matches_axis(_int_or_none(spec.get("status_id")), status_id):
            continue
        if not _rule_matches_axis(_int_or_none(spec.get("version_id")), version_id):
            continue
        if not _rule_matches_axis(_int_or_none(spec.get("priority_id")), priority_id):
            continue
        rid = _int_or_none(spec.get("id"))
        priority = _int_or_none(spec.get("priority")) or 100
        sort_order = _int_or_none(spec.get("sort_order")) or 0
        tiebreak_id = rid if rid is not None else 0
        candidates.append(
            (
                (priority, sort_order, tiebreak_id),
                MatchedRoute(
                    room_id=room_id,
                    priority=priority,
                    sort_order=sort_order,
                    notify_on_assignment=True,
                    source_table="notification_routing_rules",
                    source_id=rid,
                ),
            )
        )

    if not candidates:
        payload = {
            "event": "routing_no_match",
            "issue_id": _int_or_none(getattr(issue, "id", None)),
            "status_id": status_id,
            "version_id": version_id,
            "priority_id": priority_id,
            "matched_rules_count": 0,
            "ts": datetime.now(UTC).isoformat(),
        }
        logger.warning(json.dumps(payload, ensure_ascii=False))
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]
