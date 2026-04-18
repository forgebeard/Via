"""add display_name and department to bot_users

Revision ID: 0006_user_profile
Revises: 0005_auth_secrets
Create Date: 2026-03-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_user_profile"
down_revision: str | None = "0005_auth_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bot_users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("bot_users", sa.Column("department", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_bot_users_display_name"), "bot_users", ["display_name"], unique=False)
    op.create_index(op.f("ix_bot_users_department"), "bot_users", ["department"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_users_department"), table_name="bot_users")
    op.drop_index(op.f("ix_bot_users_display_name"), table_name="bot_users")
    op.drop_column("bot_users", "department")
    op.drop_column("bot_users", "display_name")
