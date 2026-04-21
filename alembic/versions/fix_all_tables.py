"""add redmine statuses, versions, priorities and bot columns

Revision ID: fix_all_tables
Revises: 0018_pending_notifications_dlq
Create Date: 2026-04-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fix_all_tables"
down_revision: str | None = "0018_pending_notifications_dlq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(bind: sa.Connection, name: str) -> bool:
    insp = sa.inspect(bind)
    return bool(insp.has_table(name))


def _has_column(bind: sa.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_names(bind: sa.Connection, table: str) -> set[str]:
    insp = sa.inspect(bind)
    return {i["name"] for i in insp.get_indexes(table) if i.get("name")}


def upgrade() -> None:
    """Идемпотентно: таблицы могли уже существовать (ветка 0017+0019+…)."""
    bind = op.get_bind()

    # --- redmine_statuses ---
    if not _has_table(bind, "redmine_statuses"):
        op.create_table(
            "redmine_statuses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("redmine_status_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("redmine_status_id"),
        )
        op.create_index(
            op.f("ix_redmine_statuses_is_active"), "redmine_statuses", ["is_active"], unique=False
        )
        op.create_index(
            op.f("ix_redmine_statuses_redmine_status_id"),
            "redmine_statuses",
            ["redmine_status_id"],
            unique=True,
        )
    else:
        idx_s = _index_names(bind, "redmine_statuses")
        # Колонка is_active добавляется в 0019; fix_all_tables может идти до 0019.
        if (
            _has_column(bind, "redmine_statuses", "is_active")
            and "ix_redmine_statuses_is_active" not in idx_s
        ):
            op.create_index(
                op.f("ix_redmine_statuses_is_active"), "redmine_statuses", ["is_active"], unique=False
            )
        if "ix_redmine_statuses_redmine_status_id" not in idx_s:
            op.create_index(
                op.f("ix_redmine_statuses_redmine_status_id"),
                "redmine_statuses",
                ["redmine_status_id"],
                unique=True,
            )

    # --- redmine_versions ---
    if not _has_table(bind, "redmine_versions"):
        op.create_table(
            "redmine_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("redmine_version_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("redmine_version_id"),
        )
        op.create_index(
            op.f("ix_redmine_versions_is_active"), "redmine_versions", ["is_active"], unique=False
        )
        op.create_index(
            op.f("ix_redmine_versions_redmine_version_id"),
            "redmine_versions",
            ["redmine_version_id"],
            unique=True,
        )
    else:
        idx_v = _index_names(bind, "redmine_versions")
        if (
            _has_column(bind, "redmine_versions", "is_active")
            and "ix_redmine_versions_is_active" not in idx_v
        ):
            op.create_index(
                op.f("ix_redmine_versions_is_active"), "redmine_versions", ["is_active"], unique=False
            )
        if "ix_redmine_versions_redmine_version_id" not in idx_v:
            op.create_index(
                op.f("ix_redmine_versions_redmine_version_id"),
                "redmine_versions",
                ["redmine_version_id"],
                unique=True,
            )

    # --- redmine_priorities ---
    if not _has_table(bind, "redmine_priorities"):
        op.create_table(
            "redmine_priorities",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("redmine_priority_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("redmine_priority_id"),
        )
        op.create_index(
            op.f("ix_redmine_priorities_is_active"), "redmine_priorities", ["is_active"], unique=False
        )
        op.create_index(
            op.f("ix_redmine_priorities_redmine_priority_id"),
            "redmine_priorities",
            ["redmine_priority_id"],
            unique=True,
        )
    else:
        idx_p = _index_names(bind, "redmine_priorities")
        if (
            _has_column(bind, "redmine_priorities", "is_active")
            and "ix_redmine_priorities_is_active" not in idx_p
        ):
            op.create_index(
                op.f("ix_redmine_priorities_is_active"), "redmine_priorities", ["is_active"], unique=False
            )
        if "ix_redmine_priorities_redmine_priority_id" not in idx_p:
            op.create_index(
                op.f("ix_redmine_priorities_redmine_priority_id"),
                "redmine_priorities",
                ["redmine_priority_id"],
                unique=True,
            )

    # --- bot_users / support_groups columns ---
    if _has_table(bind, "bot_users") and not _has_column(bind, "bot_users", "versions"):
        op.add_column(
            "bot_users",
            sa.Column("versions", sa.JSON(), nullable=False, server_default='["all"]'),
        )
    if _has_table(bind, "bot_users") and not _has_column(bind, "bot_users", "priorities"):
        op.add_column(
            "bot_users",
            sa.Column("priorities", sa.JSON(), nullable=False, server_default='["all"]'),
        )

    if _has_table(bind, "support_groups") and not _has_column(bind, "support_groups", "versions"):
        op.add_column(
            "support_groups",
            sa.Column("versions", sa.JSON(), nullable=False, server_default='["all"]'),
        )
    if _has_table(bind, "support_groups") and not _has_column(bind, "support_groups", "priorities"):
        op.add_column(
            "support_groups",
            sa.Column("priorities", sa.JSON(), nullable=False, server_default='["all"]'),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "support_groups"):
        if _has_column(bind, "support_groups", "priorities"):
            op.drop_column("support_groups", "priorities")
        if _has_column(bind, "support_groups", "versions"):
            op.drop_column("support_groups", "versions")
    if _has_table(bind, "bot_users"):
        if _has_column(bind, "bot_users", "priorities"):
            op.drop_column("bot_users", "priorities")
        if _has_column(bind, "bot_users", "versions"):
            op.drop_column("bot_users", "versions")

    if _has_table(bind, "redmine_priorities"):
        idx = _index_names(bind, "redmine_priorities")
        for ix in ("ix_redmine_priorities_redmine_priority_id", "ix_redmine_priorities_is_active"):
            if ix in idx:
                op.drop_index(ix, table_name="redmine_priorities")
        op.drop_table("redmine_priorities")

    if _has_table(bind, "redmine_versions"):
        idx = _index_names(bind, "redmine_versions")
        for ix in ("ix_redmine_versions_redmine_version_id", "ix_redmine_versions_is_active"):
            if ix in idx:
                op.drop_index(ix, table_name="redmine_versions")
        op.drop_table("redmine_versions")

    if _has_table(bind, "redmine_statuses"):
        idx = _index_names(bind, "redmine_statuses")
        for ix in ("ix_redmine_statuses_redmine_status_id", "ix_redmine_statuses_is_active"):
            if ix in idx:
                op.drop_index(ix, table_name="redmine_statuses")
        op.drop_table("redmine_statuses")
