"""0004_seed_notification_types

Revision ID: c4b7f6e2a901
Revises: b3f5d1f1aa72
Create Date: 2026-05-05 23:35:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4b7f6e2a901"
down_revision: str | None = "b3f5d1f1aa72"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO notification_types (key, emoji, label, is_active, sort_order)
        VALUES
            ('new', '', 'Новая задача', true, 10),
            ('reopened', '', 'Задача открыта повторно', true, 20),
            ('info', '', 'Информация предоставлена', true, 30),
            ('reminder', '', 'Напоминание', true, 40),
            ('overdue', '', 'Просроченная задача', true, 50),
            ('issue_updated', '', 'Задача обновлена', true, 60),
            ('status_change', '', 'Смена статуса', true, 70),
            ('daily_report', '', 'Утренний отчёт', true, 80)
        ON CONFLICT (key) DO UPDATE
        SET
            label = EXCLUDED.label,
            emoji = EXCLUDED.emoji,
            sort_order = EXCLUDED.sort_order;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM notification_types
        WHERE key IN (
            'new',
            'reopened',
            'info',
            'reminder',
            'overdue',
            'issue_updated',
            'status_change',
            'daily_report'
        );
        """
    )
