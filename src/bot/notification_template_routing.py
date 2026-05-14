"""Маппинг типа уведомления (send_safe / build_matrix_message_content) на имя tpl v2."""

from __future__ import annotations

from bot.logic import NOTIFICATION_TYPES

# Ключ notification_type → имя шаблона в template_loader / notification_templates.
EVENT_TO_TEMPLATE: dict[str, str] = {
    "new": "tpl_new_issue",
    "reminder": "tpl_reminder",
    "issue_updated": "tpl_task_change",
    "daily_report": "tpl_task_change",
}


def assert_event_map_covers_notification_types() -> None:
    """Все типы из NOTIFICATION_TYPES имеют целевой tpl."""
    all_keys = set(NOTIFICATION_TYPES)
    missing = all_keys - set(EVENT_TO_TEMPLATE.keys())
    if missing:
        raise AssertionError(f"EVENT_TO_TEMPLATE missing keys: {sorted(missing)}")
    unknown = set(EVENT_TO_TEMPLATE.keys()) - all_keys
    if unknown:
        raise AssertionError(
            f"EVENT_TO_TEMPLATE has keys not in NOTIFICATION_TYPES: {sorted(unknown)}"
        )


assert_event_map_covers_notification_types()
