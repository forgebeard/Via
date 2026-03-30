"""state tables + lease coordination

Revision ID: 0002_state_tables
Revises: 0001_initial
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_state_tables"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_user_leases",
        sa.Column("user_redmine_id", sa.BigInteger(), nullable=False),
        sa.Column("lease_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_redmine_id"),
    )
    op.create_index(
        op.f("ix_bot_user_leases_lease_until"),
        "bot_user_leases",
        ["lease_until"],
        unique=False,
    )

    op.create_table(
        "bot_issue_state",
        sa.Column("user_redmine_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("sent_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_journal_id", sa.Integer(), nullable=True),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_overdue_notified_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_redmine_id", "issue_id"),
    )
    op.create_index(
        op.f("ix_bot_issue_state_user_redmine_id"),
        "bot_issue_state",
        ["user_redmine_id"],
        unique=False,
    )

    op.create_table(
        "bot_state_import_markers",
        sa.Column("marker_name", sa.String(length=64), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("marker_name"),
    )


def downgrade() -> None:
    op.drop_table("bot_state_import_markers")
    op.drop_index(op.f("ix_bot_issue_state_user_redmine_id"), table_name="bot_issue_state")
    op.drop_table("bot_issue_state")
    op.drop_index(op.f("ix_bot_user_leases_lease_until"), table_name="bot_user_leases")
    op.drop_table("bot_user_leases")

