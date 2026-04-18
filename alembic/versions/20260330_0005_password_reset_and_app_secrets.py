"""password auth fields, reset tokens and encrypted app secrets

Revision ID: 0005_auth_secrets
Revises: 0004_drop_state_import_markers
Create Date: 2026-03-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_auth_secrets"
down_revision: str | None = "0004_drop_state_import_markers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bot_app_users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "bot_app_users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("bot_app_users", "session_version", server_default=None)

    op.add_column(
        "bot_sessions",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("bot_sessions", "session_version", server_default=None)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("requested_email", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_requested_email"),
        "password_reset_tokens",
        ["requested_email"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
    )

    op.create_table(
        "app_secrets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
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
    )
    op.create_index(op.f("ix_app_secrets_name"), "app_secrets", ["name"], unique=True)
    op.alter_column("app_secrets", "key_version", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_secrets_name"), table_name="app_secrets")
    op.drop_table("app_secrets")

    op.drop_constraint(
        "uq_password_reset_tokens_token_hash",
        "password_reset_tokens",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_requested_email"),
        table_name="password_reset_tokens",
    )
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_column("bot_sessions", "session_version")
    op.drop_column("bot_app_users", "session_version")
    op.drop_column("bot_app_users", "password_hash")
