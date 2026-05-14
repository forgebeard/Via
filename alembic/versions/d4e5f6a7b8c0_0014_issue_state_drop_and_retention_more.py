"""0014_issue_state_drop_and_retention_more

- DROP неиспользуемых колонок ``bot_issue_state`` (таймеры напоминаний v1, дубль journal id).
- Индексы по ``updated_at`` для batched DELETE ретеншна ``bot_watcher_cache`` и
  ``bot_issue_dedup_state``.

Revision ID: d4e5f6a7b8c0
Revises: f6b7c8d90123
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c0"
down_revision: Union[str, None] = "f6b7c8d90123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("bot_issue_state", "group_reminder_due_at")
    op.drop_column("bot_issue_state", "personal_reminder_due_at")
    op.drop_column("bot_issue_state", "reminder_count")
    op.drop_column("bot_issue_state", "last_journal_id")

    op.create_index(
        op.f("ix_bot_watcher_cache_updated_at"),
        "bot_watcher_cache",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_issue_dedup_state_updated_at"),
        "bot_issue_dedup_state",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_issue_dedup_state_updated_at"), table_name="bot_issue_dedup_state")
    op.drop_index(op.f("ix_bot_watcher_cache_updated_at"), table_name="bot_watcher_cache")

    op.add_column(
        "bot_issue_state",
        sa.Column("last_journal_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column(
            "reminder_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column("personal_reminder_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column("group_reminder_due_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(sa.text("ALTER TABLE bot_issue_state ALTER COLUMN reminder_count DROP DEFAULT"))
