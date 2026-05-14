"""0012_retention_indexes

Индексы по временным столбцам для batched DELETE ретеншна (бот, фон ночью).

Revision ID: e5f6a7b8c901
Revises: c3e9f1a4b7d2
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c901"
down_revision: Union[str, None] = "c3e9f1a4b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_pending_notifications_created_at"),
        "pending_notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_ops_audit_created_at"),
        "bot_ops_audit",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matrix_room_bindings_expires_at"),
        "matrix_room_bindings",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_sessions_expires_at"),
        "bot_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_magic_tokens_expires_at"),
        "bot_magic_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bot_magic_tokens_used_at"),
        "bot_magic_tokens",
        ["used_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_expires_at"),
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_used_at"),
        "password_reset_tokens",
        ["used_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_password_reset_tokens_used_at"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_expires_at"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_bot_magic_tokens_used_at"), table_name="bot_magic_tokens")
    op.drop_index(op.f("ix_bot_magic_tokens_expires_at"), table_name="bot_magic_tokens")
    op.drop_index(op.f("ix_bot_sessions_expires_at"), table_name="bot_sessions")
    op.drop_index(op.f("ix_matrix_room_bindings_expires_at"), table_name="matrix_room_bindings")
    op.drop_index(op.f("ix_bot_ops_audit_created_at"), table_name="bot_ops_audit")
    op.drop_index(op.f("ix_pending_notifications_created_at"), table_name="pending_notifications")
