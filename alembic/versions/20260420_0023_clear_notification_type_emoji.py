"""Очистить emoji в справочнике типов уведомлений (соответствие коду без emoji).

Revision ID: 0023_clear_nt_emoji
Revises: 0022_daily_report_tpl
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_clear_nt_emoji"
down_revision: str | None = "0022_daily_report_tpl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE notification_types SET emoji = ''"))


def downgrade() -> None:
    # Восстановление прежних значений из seed 0017 (для отката миграции).
    pairs = [
        ("new", "🆕"),
        ("status_change", "🔄"),
        ("issue_updated", "📝"),
        ("info", "✅"),
        ("overdue", "⚠️"),
        ("reminder", "⏰"),
        ("reopened", "🔁"),
    ]
    conn = op.get_bind()
    for key, em in pairs:
        conn.execute(
            sa.text("UPDATE notification_types SET emoji = :em WHERE key = :k"),
            {"em": em, "k": key},
        )
