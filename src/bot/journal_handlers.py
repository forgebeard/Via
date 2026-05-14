"""Обработка одной записи журнала: policy-маршрутизация и DLQ."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config_state import CATALOGS
from bot.logic import _cfg_for_room, describe_journal, issue_matches_cfg, should_notify
from bot.notification_template_routing import EVENT_TO_TEMPLATE
from bot.routing import resolve_policy_target_rooms
from bot.sender import resolve_room
from bot.template_context import build_issue_context, is_valid_http_issue_url
from bot.template_loader import render_named_template
from bot.time_context import notify_context_for_room
from database.dedup_repo import mark_journal_notification_sent, should_send_journal_notification
from database.dlq_repo import enqueue_notification
from matrix_send import room_send_with_retry
from preferences import can_notify

logger = logging.getLogger("redmine_bot")


def jinja_context_json_safe(ctx: dict[str, Any]) -> dict[str, Any]:
    """Контекст для DLQ / retry: JSON-serializable; при сбое — shallow-sanitize (страховка)."""
    try:
        json.dumps(ctx, ensure_ascii=False)
        return dict(ctx)
    except (TypeError, ValueError) as e:
        logger.warning("jinja_context not JSON-safe, sanitizing: %s", e)
        out: dict[str, Any] = {}
        for k, v in ctx.items():
            key = str(k)
            if v is None or isinstance(v, (str, int, float, bool)):
                out[key] = v
            elif isinstance(v, dict):
                out[key] = jinja_context_json_safe(v)
            elif isinstance(v, list):
                out[key] = [_json_safe_scalar(x) for x in v]
            else:
                out[key] = str(v)
        return out


def _json_safe_scalar(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return jinja_context_json_safe(v)
    if isinstance(v, list):
        return [_json_safe_scalar(x) for x in v]
    return str(v)


def assert_json_serializable_payload(payload: dict[str, Any]) -> None:
    json.dumps(payload)


def _policy_dedup_key(
    issue: Any,
    *,
    room_id: str,
    notification_type: str,
) -> str:
    issue_id = int(getattr(issue, "id", 0) or 0)
    status_id = str(getattr(getattr(issue, "status", None), "id", "") or "")
    version_obj = getattr(issue, "fixed_version", None) or getattr(issue, "target_version", None)
    version_id = str(getattr(version_obj, "id", "") or "")
    priority_id = str(getattr(getattr(issue, "priority", None), "id", "") or "")
    return (
        f"issue:{issue_id}:room:{room_id.strip()}:type:{notification_type}:"
        f"status:{status_id}:version:{version_id}:priority:{priority_id}"
    )


def _txn_id_from_dedup_key(dedup_key: str) -> str:
    digest = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()
    return f"issueupd_{digest[:48]}"


def _normalize_detail_prop(d: dict[str, Any]) -> str:
    return str(d.get("name") or d.get("property") or "").strip()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_assignee_detail(d: dict[str, Any]) -> bool:
    return _normalize_detail_prop(d) in ("assigned_to_id", "assigned_to")


def _event_type_from_assignee(d: dict[str, Any]) -> str:
    # Старые payload'ы journal.details: только поле property → трактуем как назначение.
    if "name" not in d and d.get("property") in ("assigned_to_id", "assigned_to"):
        return "assigned"
    old_raw = _as_text(d.get("old_value"))
    new_raw = _as_text(d.get("new_value"))
    if old_raw and new_raw:
        return "reassigned"
    if old_raw and not new_raw:
        return "unassigned"
    return "assigned"


def infer_event_type(journal: Any) -> str:
    has_notes = bool(getattr(journal, "notes", None) and str(journal.notes).strip())
    if has_notes:
        return "comment"
    try:
        for d in journal.details or []:
            prop = _normalize_detail_prop(d)
            if _is_assignee_detail(d):
                return _event_type_from_assignee(d)
            if "watcher" in prop:
                old_raw = _as_text(d.get("old_value"))
                new_raw = _as_text(d.get("new_value"))
                if old_raw and not new_raw:
                    return "watcher_removed"
                if new_raw:
                    return "watcher_added"
            if prop == "status_id":
                return "status_change"
    except Exception:
        pass
    return "issue_updated"


def journal_action_kind_for_routing(issue: Any, journal: Any) -> str:
    """
    Для сопоставления с политиками: первая запись журнала у задачи трактуется как ``created``,
    чтобы политики с ключом ``new`` могли матчиться; иначе — как ``infer_event_type``.
    """
    try:
        journals = list(getattr(issue, "journals", None) or [])
        if len(journals) == 1:
            return "created"
    except Exception:
        pass
    return infer_event_type(journal)


def former_assignee_redmine_id(journal: Any) -> int | None:
    """Из journal.details для смены исполнителя; пустой old_value = нет «бывшего» (план §4)."""
    try:
        details = journal.details or []
    except Exception:
        return None
    for d in details:
        if not isinstance(d, dict):
            continue
        prop = _normalize_detail_prop(d)
        if prop not in ("assigned_to_id", "assigned_to"):
            continue
        if "old_value" not in d:
            continue
        # Redmine REST API returns old_value/new_value as strings, even for numeric IDs.
        # "" and "0" both mean "was unassigned" (no former assignee).
        old = d.get("old_value")
        if old is None:
            continue
        s = str(old).strip()
        if s in ("", "0"):
            continue
        try:
            rid = int(s)
        except ValueError:
            continue
        if rid > 0:
            return rid
    return None


def user_cfg_by_redmine_id(users: list[dict[str, Any]], redmine_id: int) -> dict[str, Any] | None:
    for u in users:
        if int(u.get("redmine_id") or -1) == int(redmine_id):
            return u
    return None


async def watcher_cfgs_for_routing(
    session: AsyncSession,
    issue: Any,
    users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from database.watcher_cache_repo import list_bot_user_ids_for_issue

    by_bot_id = {int(u["id"]): u for u in users if u.get("id") is not None}
    out: list[dict[str, Any]] = []
    try:
        iid = int(issue.id)
    except Exception:
        return []
    for bot_uid in await list_bot_user_ids_for_issue(session, iid):
        wcfg = by_bot_id.get(int(bot_uid))
        if wcfg:
            out.append(wcfg)
    return out


def _build_structured_changes(
    journal: Any, catalogs: Any | None
) -> tuple[list[dict[str, str]], int, str]:
    from bot.logic import FIELD_NAMES, resolve_field_value

    changes: list[dict[str, str]] = []
    status_from = ""
    for d in list(getattr(journal, "details", None) or []):
        if not isinstance(d, dict):
            continue
        prop = _normalize_detail_prop(d)
        field_label = FIELD_NAMES.get(prop)
        if not field_label:
            continue
        old = resolve_field_value(prop, d.get("old_value"), catalogs)
        new = resolve_field_value(prop, d.get("new_value"), catalogs)
        old_txt = _as_text(old) or "—"
        new_txt = _as_text(new) or "—"
        if prop == "status_id":
            status_from = old_txt
        changes.append({"field": field_label, "old": old_txt, "new": new_txt})

    max_visible = 8
    extra_changes = max(0, len(changes) - max_visible)
    return changes[:max_visible], extra_changes, status_from


def _line_with_delta(current_value: str, changes: list[dict[str, str]], field_name: str) -> str:
    """
    Формирует строку поля в формате v5:
    - changed: old -> new
    - unchanged: current
    """
    for ch in changes:
        if str(ch.get("field", "")).strip() != field_name:
            continue
        old_val = _as_text(ch.get("old")) or "—"
        new_val = _as_text(ch.get("new")) or "—"
        if old_val == new_val:
            return new_val
        return f"{old_val} -> {new_val}"
    current = _as_text(current_value)
    return current or "—"


def build_journal_template_context(
    *,
    issue: Any,
    journal: Any,
    catalogs: Any | None,
    users: list[dict[str, Any]],
    event_type: str,
    extra_text: str,
) -> dict[str, Any]:
    base_ctx = build_issue_context(
        issue,
        catalogs,
        event_type=event_type,
        extra_text=extra_text,
        title="Обновление задачи",
        emoji="",
    )
    changes, extra_changes, status_from = _build_structured_changes(journal, catalogs)
    try:
        actor_name = str(getattr(getattr(journal, "user", None), "name", "") or "")
    except Exception:
        actor_name = ""
    journal_notes = _as_text(getattr(journal, "notes", None))
    assigned_from = ""
    former_rid = former_assignee_redmine_id(journal)
    if former_rid:
        former_cfg = user_cfg_by_redmine_id(users, former_rid)
        if former_cfg:
            assigned_from = str(former_cfg.get("full_name") or former_cfg.get("name") or "").strip()
    base_ctx.update(
        {
            "actor_name": actor_name,
            "journal_notes": journal_notes,
            "changes": changes,
            "extra_changes": extra_changes,
            "status_from": status_from,
            "assigned_from": assigned_from,
            "version_line": _line_with_delta(
                str(base_ctx.get("version") or "—"), changes, "Версия"
            ),
            "status_line": _line_with_delta(str(base_ctx.get("status") or "—"), changes, "Статус"),
            "priority_line": _line_with_delta(
                str(base_ctx.get("priority") or "—"), changes, "Приоритет"
            ),
            "assignee_line": _line_with_delta(
                str(base_ctx.get("assignee_name") or "—"), changes, "Назначена"
            ),
        }
    )
    return base_ctx


async def journal_render_send_or_dlq(
    client: Any,
    session: AsyncSession,
    *,
    room_id: str,
    template_name: str,
    jinja_context: dict[str, Any],
    plain_body: str,
    user_redmine_id: int,
    issue_id: int,
    notification_type: str,
    dedup_key: str,
) -> bool:
    """Рендер Jinja → Matrix; при любой ошибке — DLQ, без raise (курсор журнала вперёд).

    Ошибка до готового Matrix-тела: payload с ``needs_rerender`` и JSON-safe контекстом (A1).
    Ошибка после рендера: payload = готовое тело Matrix (повтор без рендера).
    """
    content: dict[str, Any] | None = None
    if template_name in {"tpl_new_issue", "tpl_task_change"}:
        issue_url = str(jinja_context.get("issue_url") or "").strip()
        if not is_valid_http_issue_url(issue_url):
            logger.error(
                "journal_skip_invalid_issue_url issue_id=%s room=%s template=%s issue_url=%r",
                issue_id,
                (room_id or "")[:32],
                template_name,
                issue_url,
            )
            return False
    try:
        html, plain_tpl = await render_named_template(session, template_name, jinja_context)
        matrix_plain = plain_tpl if plain_tpl is not None else plain_body
        content = {
            "msgtype": "m.text",
            "body": matrix_plain,
            "format": "org.matrix.custom.html",
            "formatted_body": html,
        }
        resolved = await resolve_room(client, room_id)
        await room_send_with_retry(
            client, resolved, content, txn_id=_txn_id_from_dedup_key(dedup_key)
        )
        return True
    except Exception as e:
        err = str(e)
        if content is not None:
            try:
                assert_json_serializable_payload(content)
                await enqueue_notification(
                    session,
                    user_redmine_id=user_redmine_id,
                    issue_id=issue_id,
                    room_id=room_id,
                    notification_type=notification_type,
                    payload=content,
                    error=err,
                )
            except Exception as dlq_e:
                logger.error("journal_dlq_enqueue_failed #%s: %s", issue_id, dlq_e, exc_info=True)
        else:
            dlq_payload = {
                "needs_rerender": True,
                "template_name": template_name,
                "jinja_context": jinja_context_json_safe(jinja_context),
                "plain_body": plain_body,
                "issue_id": int(issue_id),
                "room_id": room_id,
                "notification_type": notification_type,
            }
            try:
                assert_json_serializable_payload(dlq_payload)
                await enqueue_notification(
                    session,
                    user_redmine_id=user_redmine_id,
                    issue_id=issue_id,
                    room_id=room_id,
                    notification_type=notification_type,
                    payload=dlq_payload,
                    error=err,
                )
            except Exception as dlq_e:
                logger.error("journal_dlq_enqueue_failed #%s: %s", issue_id, dlq_e, exc_info=True)
        logger.warning(
            "journal_notify_dlq issue_id=%s room=%s type=%s: %s",
            issue_id,
            (room_id or "")[:32],
            notification_type,
            err,
            exc_info=True,
        )
    return False


def _effective_sender_redmine_id(assignee_cfg: dict[str, Any] | None, journal: Any) -> int:
    if assignee_cfg:
        try:
            rid = int(assignee_cfg.get("redmine_id") or 0)
        except (TypeError, ValueError):
            rid = 0
        if rid > 0:
            return rid
    try:
        return int(getattr(getattr(journal, "user", None), "id", 0) or 0)
    except (TypeError, ValueError):
        return 0


async def handle_journal_entry(
    client: Any,
    session: AsyncSession,
    *,
    issue: Any,
    journal: Any,
    assignee_cfg: dict[str, Any] | None,
    routes_cfg: dict[str, Any] | None,
    groups: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> None:
    """Доставка уведомлений только по policy-маршрутам."""
    cats = CATALOGS
    event_type = infer_event_type(journal)
    extra = describe_journal(journal, skip_status=False, catalogs=cats) or ""

    base_ctx = build_journal_template_context(
        issue=issue,
        journal=journal,
        catalogs=cats,
        users=users,
        event_type=event_type,
        extra_text=extra,
    )

    watcher_cfgs_r = await watcher_cfgs_for_routing(session, issue, users)
    policy_rooms = resolve_policy_target_rooms(
        issue,
        routes_cfg,
        action_kind=journal_action_kind_for_routing(issue, journal),
        users=users,
        groups=groups,
        actor_redmine_id=int(getattr(getattr(journal, "user", None), "id", 0) or 0),
        log_prefix="journal_routing_policy",
        assignee_cfg=assignee_cfg,
        watcher_cfgs=watcher_cfgs_r,
    )
    if not policy_rooms.deliveries:
        return

    candidates: list[dict[str, Any]] = [
        *([assignee_cfg] if assignee_cfg else []),
        *users,
        *groups,
        *watcher_cfgs_r,
    ]
    room_to_cfgs: dict[str, list[dict[str, Any]]] = {}
    for cfg in candidates:
        room = str(cfg.get("room") or "").strip()
        if not room:
            continue
        room_to_cfgs.setdefault(room, []).append(cfg)

    plain = f"#{issue.id} {base_ctx['subject']}: {event_type}"
    issue_priority = str(getattr(getattr(issue, "priority", None), "name", "") or "")
    for room_id, ntype in policy_rooms.deliveries:
        cfgs = room_to_cfgs.get(room_id, [])
        if not cfgs:
            continue
        allowed_now = False
        for cfg in cfgs:
            if not issue_matches_cfg(issue, cfg):
                continue
            if not should_notify(cfg, ntype):
                continue
            effective_cfg = _cfg_for_room(cfg, room_id)
            nctx = notify_context_for_room(cfg, room_id)
            if can_notify(effective_cfg, priority=issue_priority, context=nctx):
                allowed_now = True
                break
        if not allowed_now:
            logger.debug("journal_policy_skip_time_or_dnd issue=%s room=%s", issue.id, room_id[:24])
            continue
        if ntype in {"new", "issue_updated"}:
            should_send = await should_send_journal_notification(
                session,
                issue=issue,
                room_id=room_id,
                notification_type=ntype,
            )
            if not should_send:
                logger.debug(
                    "journal_policy_dedup_skip issue=%s room=%s type=%s",
                    issue.id,
                    room_id[:24],
                    ntype,
                )
                continue

        template_name = EVENT_TO_TEMPLATE.get(ntype, "tpl_task_change")
        delivered = await journal_render_send_or_dlq(
            client,
            session,
            room_id=room_id,
            template_name=template_name,
            jinja_context=base_ctx,
            plain_body=plain,
            user_redmine_id=_effective_sender_redmine_id(assignee_cfg, journal),
            issue_id=int(issue.id),
            notification_type=ntype,
            dedup_key=_policy_dedup_key(issue, room_id=room_id, notification_type=ntype),
        )
        if delivered and ntype in {"new", "issue_updated"}:
            await mark_journal_notification_sent(
                session,
                issue=issue,
                room_id=room_id,
                notification_type=ntype,
            )
