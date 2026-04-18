"""initial bot config tables

Revision ID: 0001_initial
Revises:
Create Date: 2025-03-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("redmine_id", sa.Integer(), nullable=False),
        sa.Column("room", sa.Text(), nullable=False),
        sa.Column("notify", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("work_hours", sa.String(length=32), nullable=True),
        sa.Column("work_days", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dnd", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("redmine_id"),
    )

    op.create_table(
        "status_room_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status_key", sa.String(length=512), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("status_key"),
    )

    op.create_table(
        "version_room_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_key", sa.String(length=512), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_key"),
    )


def downgrade() -> None:
    op.drop_table("version_room_routes")
    op.drop_table("status_room_routes")
    op.drop_table("bot_users")
