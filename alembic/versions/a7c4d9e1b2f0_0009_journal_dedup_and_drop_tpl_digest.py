"""0009_journal_dedup_and_drop_tpl_digest

Revision ID: a7c4d9e1b2f0
Revises: 9b7c2d4e6f8a
Create Date: 2026-05-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c4d9e1b2f0"
down_revision: Union[str, None] = "9b7c2d4e6f8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_issue_dedup_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column("status_id", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("priority_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issue_id",
            "room_id",
            "notification_type",
            name="uq_bot_issue_dedup_issue_room_type",
        ),
    )
    op.create_index(
        op.f("ix_bot_issue_dedup_state_issue_id"),
        "bot_issue_dedup_state",
        ["issue_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_issue_dedup_state_notification_type"),
        "bot_issue_dedup_state",
        ["notification_type"],
        unique=False,
    )

    op.execute("DELETE FROM notification_templates WHERE name = 'tpl_digest'")


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_issue_dedup_state_notification_type"), table_name="bot_issue_dedup_state")
    op.drop_index(op.f("ix_bot_issue_dedup_state_issue_id"), table_name="bot_issue_dedup_state")
    op.drop_table("bot_issue_dedup_state")
