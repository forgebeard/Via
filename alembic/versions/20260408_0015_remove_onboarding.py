"""Remove onboarding: drop onboarding_sessions table and redmine_api_key_* columns from bot_users.

Revision ID: 0015_remove_onboarding
Revises: 0013_bot_user_timezone
Create Date: 2026-04-08
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0015_remove_onboarding"
down_revision: str | None = "0014_bot_ops_audit_crud"


def upgrade() -> None:
    # Drop onboarding_sessions table
    op.drop_index(
        "ix_onboarding_sessions_sender_mxid", table_name="onboarding_sessions", if_exists=True
    )
    op.drop_table("onboarding_sessions", if_exists=True)

    # Remove redmine_api_key_* columns from bot_users (if they exist)
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("bot_users")]

    for col in (
        "redmine_api_key_ciphertext",
        "redmine_api_key_nonce",
        "redmine_api_key_key_version",
    ):
        if col in columns:
            op.drop_column("bot_users", col)


def downgrade() -> None:
    # Re-add columns
    op.add_column(
        "bot_users", sa.Column("redmine_api_key_ciphertext", sa.LargeBinary(), nullable=True)
    )
    op.add_column("bot_users", sa.Column("redmine_api_key_nonce", sa.LargeBinary(), nullable=True))
    op.add_column(
        "bot_users",
        sa.Column(
            "redmine_api_key_key_version", sa.SmallInteger(), nullable=False, server_default="1"
        ),
    )

    # Recreate table
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Text(), unique=True, nullable=False),
        sa.Column("sender_mxid", sa.Text(), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("redmine_id", sa.BigInteger(), nullable=True),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("department_name", sa.Text(), nullable=True),
        sa.Column("work_hours", sa.String(32), nullable=True),
        sa.Column("work_days", sa.JSON(), nullable=True),
        sa.Column("notify", sa.JSON(), nullable=True),
        sa.Column("change_mode", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "existing_bot_user_id",
            sa.Integer(),
            sa.ForeignKey("bot_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_onboarding_sessions_sender_mxid", "onboarding_sessions", ["sender_mxid"])
