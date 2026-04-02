"""Matrix DM onboarding sessions + персональный API-ключ Redmine у bot_users.

Revision ID: 0012_matrix_onboarding
Revises: 0011_group_user_version_routes
Create Date: 2026-04-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_matrix_onboarding"
down_revision: Union[str, None] = "0011_group_user_version_routes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column("redmine_api_key_ciphertext", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "bot_users",
        sa.Column("redmine_api_key_nonce", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "bot_users",
        sa.Column("redmine_api_key_key_version", sa.SmallInteger(), nullable=False, server_default="1"),
    )

    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.Column("sender_mxid", sa.Text(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("redmine_id", sa.BigInteger(), nullable=True),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("department_name", sa.Text(), nullable=True),
        sa.Column("work_hours", sa.String(length=32), nullable=True),
        sa.Column("work_days", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notify", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("change_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("existing_bot_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["existing_bot_user_id"],
            ["bot_users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", name="uq_onboarding_sessions_room_id"),
    )
    op.create_index(
        "ix_onboarding_sessions_sender_mxid",
        "onboarding_sessions",
        ["sender_mxid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_sessions_sender_mxid", table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")
    op.drop_column("bot_users", "redmine_api_key_key_version")
    op.drop_column("bot_users", "redmine_api_key_nonce")
    op.drop_column("bot_users", "redmine_api_key_ciphertext")
