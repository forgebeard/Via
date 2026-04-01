"""Поля расписания и типов уведомлений для support_groups.

Revision ID: 0010_support_group_schedule
Revises: 0009_drop_legacy_org_seeds
Create Date: 2026-04-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_support_group_schedule"
down_revision: Union[str, None] = "0009_drop_legacy_org_seeds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "support_groups",
        sa.Column(
            "notify",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='["all"]',
        ),
    )
    op.add_column("support_groups", sa.Column("work_hours", sa.String(length=32), nullable=True))
    op.add_column(
        "support_groups",
        sa.Column("work_days", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "support_groups",
        sa.Column("dnd", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("support_groups", "dnd")
    op.drop_column("support_groups", "work_days")
    op.drop_column("support_groups", "work_hours")
    op.drop_column("support_groups", "notify")
