"""Добавляет timezone в bot_users.

Revision ID: 0013_bot_user_timezone
Revises: 0011_group_user_version_routes
Create Date: 2026-04-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_bot_user_timezone"
down_revision: Union[str, None] = "0011_group_user_version_routes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bot_users", sa.Column("timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("bot_users", "timezone")
