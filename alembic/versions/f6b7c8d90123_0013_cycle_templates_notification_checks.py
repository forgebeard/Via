"""0013_cycle_templates_notification_checks

- Удалить неразрешённые строки из cycle_settings (см. database.cycle_settings_known).
- Плейсхолдер template-рядов для tpl v2 без override (ссылки на файлы из git).
- CHECK на notification_type в pending_notifications и bot_issue_dedup_state.
- Принудительно привести устаревшие notification_type к issue_updated перед CHECK.

Revision ID: f6b7c8d90123
Revises: e5f6a7b8c901
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "f6b7c8d90123"
down_revision: Union[str, None] = "e5f6a7b8c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KNOWN_NT = ("new", "reminder", "issue_updated", "daily_report")

_TEMPLATES = ("tpl_new_issue", "tpl_task_change", "tpl_reminder")


def upgrade() -> None:
    from database.cycle_settings_known import CYCLE_SETTINGS_RECOGNIZED_KEYS

    keys_sql = ", ".join(f"'{k}'" for k in sorted(CYCLE_SETTINGS_RECOGNIZED_KEYS))
    op.execute(text(f"DELETE FROM cycle_settings WHERE key NOT IN ({keys_sql})"))

    for tpl in _TEMPLATES:
        op.execute(
            text(
                """
                INSERT INTO notification_templates (name, body_html, body_plain, updated_by)
                SELECT CAST(:name AS VARCHAR(100)), CAST(NULL AS TEXT), CAST(NULL AS TEXT),
                       CAST(NULL AS VARCHAR(100))
                WHERE NOT EXISTS (
                    SELECT 1 FROM notification_templates nt WHERE nt.name = :name
                )
                """
            ).bindparams(name=tpl)
        )

    placeholders = ",".join(f"'{x}'" for x in _KNOWN_NT)

    op.execute(
        text(
            f"""
            UPDATE pending_notifications
            SET notification_type = 'issue_updated'
            WHERE notification_type NOT IN ({placeholders})
            """
        )
    )
    op.execute(
        text(
            f"""
            UPDATE bot_issue_dedup_state
            SET notification_type = 'issue_updated'
            WHERE notification_type NOT IN ({placeholders})
            """
        )
    )

    op.execute(
        text(
            f"""
            ALTER TABLE pending_notifications
            ADD CONSTRAINT ck_pending_notifications_notification_type_v1
            CHECK (notification_type IN ({placeholders}))
            """
        )
    )
    op.execute(
        text(
            f"""
            ALTER TABLE bot_issue_dedup_state
            ADD CONSTRAINT ck_bot_issue_dedup_notification_type_v1
            CHECK (notification_type IN ({placeholders}))
            """
        )
    )


def downgrade() -> None:
    # CHECK-и добавлены в upgrade; снимаем явно (имена фиксированы).
    op.drop_constraint(
        "ck_bot_issue_dedup_notification_type_v1",
        "bot_issue_dedup_state",
        type_="check",
    )
    op.drop_constraint(
        "ck_pending_notifications_notification_type_v1",
        "pending_notifications",
        type_="check",
    )
    # Плейсхолдеры шаблонов из upgrade: убираем только незаполненные строки.
    for tpl in _TEMPLATES:
        op.execute(
            text(
                """
                DELETE FROM notification_templates
                WHERE name = :name
                  AND body_html IS NULL
                  AND body_plain IS NULL
                """
            ).bindparams(name=tpl)
        )
    # Удалённые ключи cycle_settings не восстанавливаем (best-effort downgrade).
