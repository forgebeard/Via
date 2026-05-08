"""0002_notification_routing_rules

Revision ID: a91db4a3d2e1
Revises: 51880363396d
Create Date: 2026-05-05 16:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a91db4a3d2e1"
down_revision: Union[str, None] = "51880363396d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_routing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_room_id", sa.Text(), nullable=False),
        sa.Column("status_id", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("priority_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["priority_id"], ["redmine_priorities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["status_id"], ["redmine_statuses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["version_id"], ["redmine_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_routing_rules_enabled_priority_sort_order",
        "notification_routing_rules",
        ["enabled", "priority", "sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_priority"),
        "notification_routing_rules",
        ["priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_sort_order"),
        "notification_routing_rules",
        ["sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_enabled"),
        "notification_routing_rules",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_status_id"),
        "notification_routing_rules",
        ["status_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_version_id"),
        "notification_routing_rules",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_routing_rules_priority_id"),
        "notification_routing_rules",
        ["priority_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_routing_rules_priority_id"), table_name="notification_routing_rules")
    op.drop_index(op.f("ix_notification_routing_rules_version_id"), table_name="notification_routing_rules")
    op.drop_index(op.f("ix_notification_routing_rules_status_id"), table_name="notification_routing_rules")
    op.drop_index(op.f("ix_notification_routing_rules_enabled"), table_name="notification_routing_rules")
    op.drop_index(op.f("ix_notification_routing_rules_sort_order"), table_name="notification_routing_rules")
    op.drop_index(op.f("ix_notification_routing_rules_priority"), table_name="notification_routing_rules")
    op.drop_index(
        "ix_notification_routing_rules_enabled_priority_sort_order",
        table_name="notification_routing_rules",
    )
    op.drop_table("notification_routing_rules")
