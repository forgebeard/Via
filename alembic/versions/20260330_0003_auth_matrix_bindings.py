"""auth (magic-link) + matrix room bindings

Revision ID: 0003_auth_matrix_bindings
Revises: 0002_state_tables
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_auth_matrix_bindings"
down_revision: Union[str, None] = "0002_state_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_app_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("redmine_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(op.f("ix_bot_app_users_email"), "bot_app_users", ["email"], unique=True)
    op.create_index(op.f("ix_bot_app_users_redmine_id"), "bot_app_users", ["redmine_id"], unique=True)

    op.create_table(
        "bot_magic_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_bot_magic_tokens_email"), "bot_magic_tokens", ["email"], unique=False)
    op.create_unique_constraint("uq_bot_magic_tokens_token_hash", "bot_magic_tokens", ["token_hash"])

    op.create_table(
        "bot_sessions",
        sa.Column(
            "session_token",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Если миграция уже частично исполнялась (ошибка на предыдущем запуске),
    # индекс мог успеть появиться. Делаем повторный upgrade безопасным.
    op.execute("DROP INDEX IF EXISTS ix_bot_sessions_user_id")
    op.create_index(op.f("ix_bot_sessions_user_id"), "bot_sessions", ["user_id"], unique=False)

    op.create_table(
        "matrix_room_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("redmine_id", sa.BigInteger(), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.Column("verify_code_hash", sa.Text(), nullable=False),
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
        op.f("ix_matrix_room_bindings_user_id"), "matrix_room_bindings", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_matrix_room_bindings_redmine_id"),
        "matrix_room_bindings",
        ["redmine_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_matrix_room_bindings_redmine_id"), table_name="matrix_room_bindings")
    op.drop_index(op.f("ix_matrix_room_bindings_user_id"), table_name="matrix_room_bindings")
    op.drop_table("matrix_room_bindings")

    op.drop_index(op.f("ix_bot_sessions_user_id"), table_name="bot_sessions")
    op.drop_table("bot_sessions")

    op.drop_constraint("uq_bot_magic_tokens_token_hash", "bot_magic_tokens", type_="unique")
    op.drop_index(op.f("ix_bot_magic_tokens_email"), table_name="bot_magic_tokens")
    op.drop_table("bot_magic_tokens")

    op.drop_index(op.f("ix_bot_app_users_redmine_id"), table_name="bot_app_users")
    op.drop_index(op.f("ix_bot_app_users_email"), table_name="bot_app_users")
    op.drop_table("bot_app_users")

