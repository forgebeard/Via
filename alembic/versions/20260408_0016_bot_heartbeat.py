"""Add bot_heartbeat table for monitoring bot liveness.

Revision ID: 0016_bot_heartbeat
Revises: 0015_remove_onboarding
Create Date: 2026-04-08
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0016_bot_heartbeat"
down_revision: Union[str, None] = "0015_remove_onboarding"


def upgrade() -> None:
    op.create_table(
        "bot_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instance_id",
            PGUUID(as_uuid=True),
            unique=True,
            nullable=False,
            index=True,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("bot_heartbeat")
