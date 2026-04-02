"""
Строки CRUD для файла «События» ([ADMIN]) при ADMIN_EVENTS_LOG_CRUD=1.

Формат согласован с _append_ops_to_events_log в admin_main: префикс [ADMIN]
добавляется там; здесь только тело сообщения.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from mail import mask_identifier

# Ключи details (в любом регистре), значения которых не попадают в лог.
_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "access_token",
        "refresh_token",
        "private_key",
        "credential",
    }
)

MAX_DETAIL_SCALAR_LEN = 120


def want_admin_events_log_crud() -> bool:
    """ADMIN_EVENTS_LOG_CRUD=1|true|yes|on — писать CRUD в файл событий."""
    v = (os.getenv("ADMIN_EVENTS_LOG_CRUD") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def want_admin_audit_crud_db() -> bool:
    """
    Писать CRUD в таблицу bot_ops_audit (action=ADMIN_CRUD).

    ADMIN_AUDIT_CRUD_DB: явно 0/false/off — не писать; 1/true/on — писать.
    Если не задано — как ADMIN_EVENTS_LOG_CRUD (включение файла включает и БД).
    """
    raw = (os.getenv("ADMIN_AUDIT_CRUD_DB") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return want_admin_events_log_crud()


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return False
    if k in _SENSITIVE_KEY_FRAGMENTS:
        return True
    for frag in _SENSITIVE_KEY_FRAGMENTS:
        if frag in k:
            return True
    if k.endswith("_api_key") or k.endswith("_secret"):
        return True
    return False


def sanitize_audit_details(details: Mapping[str, Any] | None) -> dict[str, str]:
    """Плоский словарь строк для лога; секреты и длинные значения режутся."""
    out: dict[str, str] = {}
    if not details:
        return out
    for raw_k, raw_v in details.items():
        k = str(raw_k).strip()
        if not k or _is_sensitive_key(k):
            out[k or "key"] = "***REDACTED***" if k else "***"
            continue
        if raw_v is None:
            continue
        if isinstance(raw_v, (dict, list, tuple, set)):
            out[k] = "[omitted]"
            continue
        if isinstance(raw_v, bool):
            s = "1" if raw_v else "0"
        elif isinstance(raw_v, (int, float)):
            s = str(raw_v)
        else:
            s = str(raw_v).replace("\n", " ").replace("\r", " ").strip()
        if len(s) > MAX_DETAIL_SCALAR_LEN:
            s = s[: MAX_DETAIL_SCALAR_LEN - 3] + "..."
        # без пробелов в значении — проще читать в хвосте лога
        s = s.replace(" ", "_")
        out[k] = s
    return out


def actor_label_for_crud_log(user: Any | None) -> str:
    """Маскированный логин панели (как для события входа)."""
    if user is None:
        return "unknown"
    login = getattr(user, "login", None)
    if not login:
        return "unknown"
    return mask_identifier(str(login).strip())


def format_crud_line(
    entity_type: str,
    action: str,
    actor: str,
    details: Mapping[str, Any] | None = None,
) -> str:
    """
    Одна строка без перевода строки. Пример:
    CRUD bot_user/create id=1 redmine_id=42 by=ad***
    """
    et = (entity_type or "unknown").strip().replace("\n", " ")
    act = (action or "unknown").strip().replace("\n", " ")
    safe_actor = (actor or "unknown").replace("\n", " ").strip()
    parts: list[str] = [f"CRUD {et}/{act}"]
    d = sanitize_audit_details(details)
    for key in sorted(d.keys()):
        parts.append(f"{key}={d[key]}")
    parts.append(f"by={safe_actor}")
    return " ".join(parts)
