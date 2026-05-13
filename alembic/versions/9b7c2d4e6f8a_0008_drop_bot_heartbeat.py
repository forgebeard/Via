"""0008_drop_bot_heartbeat

Revision ID: 9b7c2d4e6f8a
Revises: f1a2b3c4d5e6
Create Date: 2026-05-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9b7c2d4e6f8a"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_bot_heartbeat_instance_id", table_name="bot_heartbeat")
    op.drop_table("bot_heartbeat")


def downgrade() -> None:
    op.create_table(
        "bot_heartbeat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id"),
    )
    op.create_index(
        "ix_bot_heartbeat_instance_id",
        "bot_heartbeat",
        ["instance_id"],
        unique=True,
    )
