"""Add reference data tables: redmine_statuses, notification_types, cycle_settings.

Revision ID: 0017_reference_data
Revises: 0016_bot_heartbeat
Create Date: 2026-04-08
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_reference_data"
down_revision: Union[str, None] = "0016_bot_heartbeat"


def upgrade() -> None:
    # Redmine statuses
    op.create_table(
        "redmine_statuses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("redmine_status_id", sa.Integer(), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Notification types
    op.create_table(
        "notification_types",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("emoji", sa.String(16), nullable=False, server_default="📝"),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Cycle settings
    op.create_table(
        "cycle_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Seed default notification types
    op.bulk_insert(
        sa.table(
            "notification_types",
            sa.column("key", sa.String),
            sa.column("emoji", sa.String),
            sa.column("label", sa.String),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {"key": "new", "emoji": "🆕", "label": "Новая задача", "sort_order": 1},
            {"key": "status_change", "emoji": "🔄", "label": "Смена статуса", "sort_order": 2},
            {"key": "issue_updated", "emoji": "📝", "label": "Задача обновлена", "sort_order": 3},
            {"key": "info", "emoji": "✅", "label": "Информация предоставлена", "sort_order": 4},
            {"key": "overdue", "emoji": "⚠️", "label": "Просроченная задача", "sort_order": 5},
            {"key": "reminder", "emoji": "⏰", "label": "Напоминание", "sort_order": 6},
            {"key": "reopened", "emoji": "🔁", "label": "Открыто повторно", "sort_order": 7},
        ],
    )

    # Seed default cycle settings
    op.bulk_insert(
        sa.table(
            "cycle_settings",
            sa.column("key", sa.String),
            sa.column("value", sa.Text),
            sa.column("description", sa.String),
        ),
        [
            {"key": "check_interval", "value": "90", "description": "Интервал опроса Redmine (сек)"},
            {"key": "reminder_after", "value": "3600", "description": "Напоминать через (сек)"},
            {"key": "group_repeat_seconds", "value": "1800", "description": "Повтор группового уведомления (сек)"},
        ],
    )


def downgrade() -> None:
    op.drop_table("cycle_settings")
    op.drop_table("notification_types")
    op.drop_table("redmine_statuses")
