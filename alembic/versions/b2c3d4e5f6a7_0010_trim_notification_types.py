"""0010_trim_notification_types

Оставить в справочнике ключи: new, reminder, issue_updated, daily_report.
Перед удалением строк — переназначить FK политик и нормализовать строки/JSON.

Revision ID: b2c3d4e5f6a7
Revises: a7c4d9e1b2f0
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a7c4d9e1b2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE routing_policies rp
        SET notification_type_id = (
            SELECT id FROM notification_types WHERE key = 'issue_updated' LIMIT 1
        )
        WHERE notification_type_id IN (
            SELECT id FROM notification_types WHERE key IN ('reopened', 'info', 'overdue', 'status_change')
        )
        """
    )
    op.execute(
        """
        UPDATE bot_users u
        SET notify = COALESCE(
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN token IN ('reopened', 'info', 'overdue', 'status_change')
                        THEN to_jsonb('issue_updated'::text)
                        ELSE to_jsonb(token)
                    END
                )
                FROM jsonb_array_elements_text(COALESCE(u.notify, '[]'::jsonb)) AS t(token)
            ),
            '[]'::jsonb
        )
        WHERE notify IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(COALESCE(u.notify, '[]'::jsonb)) AS x(v)
            WHERE x.v IN ('reopened', 'info', 'overdue', 'status_change')
          )
        """
    )
    op.execute(
        """
        UPDATE support_groups g
        SET notify = COALESCE(
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN token IN ('reopened', 'info', 'overdue', 'status_change')
                        THEN to_jsonb('issue_updated'::text)
                        ELSE to_jsonb(token)
                    END
                )
                FROM jsonb_array_elements_text(COALESCE(g.notify, '[]'::jsonb)) AS t(token)
            ),
            '[]'::jsonb
        )
        WHERE notify IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(COALESCE(g.notify, '[]'::jsonb)) AS x(v)
            WHERE x.v IN ('reopened', 'info', 'overdue', 'status_change')
          )
        """
    )
    op.execute(
        """
        UPDATE pending_notifications
        SET notification_type = 'issue_updated'
        WHERE notification_type IN ('reopened', 'info', 'overdue', 'status_change')
        """
    )
    op.execute(
        """
        UPDATE bot_issue_dedup_state
        SET notification_type = 'issue_updated'
        WHERE notification_type IN ('reopened', 'info', 'overdue', 'status_change')
        """
    )
    op.execute(
        """
        DELETE FROM notification_types
        WHERE key IN ('reopened', 'info', 'overdue', 'status_change')
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        INSERT INTO notification_types (key, emoji, label, is_active, sort_order)
        VALUES
            ('reopened', '', 'Задача открыта повторно', true, 20),
            ('info', '', 'Информация предоставлена', true, 30),
            ('overdue', '', 'Просроченная задача', true, 50),
            ('status_change', '', 'Смена статуса', true, 70)
        ON CONFLICT (key) DO NOTHING
        """
    )
