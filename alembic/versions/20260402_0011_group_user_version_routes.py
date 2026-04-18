"""Маршруты по версии Redmine для групп и пользователей бота.

Revision ID: 0011_group_user_version_routes
Revises: 0010_support_group_schedule
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_group_user_version_routes"
down_revision: str | None = "0010_support_group_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_version_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("version_key", sa.String(length=512), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["support_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "version_key", name="uq_group_version_routes_group_version"
        ),
    )
    op.create_index(
        op.f("ix_group_version_routes_group_id"),
        "group_version_routes",
        ["group_id"],
        unique=False,
    )

    op.create_table(
        "user_version_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bot_user_id", sa.Integer(), nullable=False),
        sa.Column("version_key", sa.String(length=512), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["bot_user_id"], ["bot_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bot_user_id", "version_key", name="uq_user_version_routes_user_version"
        ),
    )
    op.create_index(
        op.f("ix_user_version_routes_bot_user_id"),
        "user_version_routes",
        ["bot_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_version_routes_bot_user_id"), table_name="user_version_routes")
    op.drop_table("user_version_routes")
    op.drop_index(op.f("ix_group_version_routes_group_id"), table_name="group_version_routes")
    op.drop_table("group_version_routes")
