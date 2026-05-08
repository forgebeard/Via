"""0003_policy_routing_v3

Revision ID: b3f5d1f1aa72
Revises: a91db4a3d2e1
Create Date: 2026-05-05 22:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f5d1f1aa72"
down_revision: Union[str, None] = "a91db4a3d2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notification_type_id", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.String(length=16), server_default="both", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["notification_type_id"], ["notification_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_routing_policies_enabled"), "routing_policies", ["enabled"], unique=False)
    op.create_index(
        op.f("ix_routing_policies_notification_type_id"),
        "routing_policies",
        ["notification_type_id"],
        unique=False,
    )

    op.create_table(
        "routing_policy_statuses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("status_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["status_id"], ["redmine_statuses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "status_id", name="uq_routing_policy_status"),
    )
    op.create_index(op.f("ix_routing_policy_statuses_policy_id"), "routing_policy_statuses", ["policy_id"], unique=False)
    op.create_index(op.f("ix_routing_policy_statuses_status_id"), "routing_policy_statuses", ["status_id"], unique=False)

    op.create_table(
        "routing_policy_priorities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("priority_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["priority_id"], ["redmine_priorities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "priority_id", name="uq_routing_policy_priority"),
    )
    op.create_index(op.f("ix_routing_policy_priorities_policy_id"), "routing_policy_priorities", ["policy_id"], unique=False)
    op.create_index(op.f("ix_routing_policy_priorities_priority_id"), "routing_policy_priorities", ["priority_id"], unique=False)

    op.create_table(
        "routing_policy_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["redmine_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version_id", name="uq_routing_policy_version"),
    )
    op.create_index(op.f("ix_routing_policy_versions_policy_id"), "routing_policy_versions", ["policy_id"], unique=False)
    op.create_index(op.f("ix_routing_policy_versions_version_id"), "routing_policy_versions", ["version_id"], unique=False)

    op.create_table(
        "routing_policy_target_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "user_id", name="uq_routing_policy_target_user"),
    )
    op.create_index(op.f("ix_routing_policy_target_users_policy_id"), "routing_policy_target_users", ["policy_id"], unique=False)
    op.create_index(op.f("ix_routing_policy_target_users_user_id"), "routing_policy_target_users", ["user_id"], unique=False)

    op.create_table(
        "routing_policy_target_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["routing_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["support_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "group_id", name="uq_routing_policy_target_group"),
    )
    op.create_index(op.f("ix_routing_policy_target_groups_policy_id"), "routing_policy_target_groups", ["policy_id"], unique=False)
    op.create_index(op.f("ix_routing_policy_target_groups_group_id"), "routing_policy_target_groups", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_routing_policy_target_groups_group_id"), table_name="routing_policy_target_groups")
    op.drop_index(op.f("ix_routing_policy_target_groups_policy_id"), table_name="routing_policy_target_groups")
    op.drop_table("routing_policy_target_groups")
    op.drop_index(op.f("ix_routing_policy_target_users_user_id"), table_name="routing_policy_target_users")
    op.drop_index(op.f("ix_routing_policy_target_users_policy_id"), table_name="routing_policy_target_users")
    op.drop_table("routing_policy_target_users")
    op.drop_index(op.f("ix_routing_policy_versions_version_id"), table_name="routing_policy_versions")
    op.drop_index(op.f("ix_routing_policy_versions_policy_id"), table_name="routing_policy_versions")
    op.drop_table("routing_policy_versions")
    op.drop_index(op.f("ix_routing_policy_priorities_priority_id"), table_name="routing_policy_priorities")
    op.drop_index(op.f("ix_routing_policy_priorities_policy_id"), table_name="routing_policy_priorities")
    op.drop_table("routing_policy_priorities")
    op.drop_index(op.f("ix_routing_policy_statuses_status_id"), table_name="routing_policy_statuses")
    op.drop_index(op.f("ix_routing_policy_statuses_policy_id"), table_name="routing_policy_statuses")
    op.drop_table("routing_policy_statuses")
    op.drop_index(op.f("ix_routing_policies_notification_type_id"), table_name="routing_policies")
    op.drop_index(op.f("ix_routing_policies_enabled"), table_name="routing_policies")
    op.drop_table("routing_policies")
