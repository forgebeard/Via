"""Journal engine v2: cursors, digests, watcher cache, templates, route columns, issue state timers.

Revision ID: 0021_journal_engine_v2
Revises: 0020_merge_heads
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0021_journal_engine_v2"
down_revision: str | None = "0020_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_issue_journal_cursor",
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("last_journal_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("issue_id", name="pk_bot_issue_journal_cursor"),
    )

    op.create_table(
        "pending_digests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_subject", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("journal_id", sa.Integer(), nullable=True),
        sa.Column("journal_notes", sa.Text(), nullable=True),
        sa.Column("status_name", sa.String(100), nullable=True),
        sa.Column("assigned_to", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pending_digests"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["bot_users.id"],
            name="fk_pending_digests_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_pending_digests_user_created",
        "pending_digests",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "bot_watcher_cache",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "issue_id", name="pk_bot_watcher_cache"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["bot_users.id"],
            name="fk_bot_watcher_cache_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_bot_watcher_cache_issue_id", "bot_watcher_cache", ["issue_id"], unique=False)

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_plain", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_notification_templates"),
        sa.UniqueConstraint("name", name="uq_notification_templates_name"),
    )

    _add_route_columns("status_room_routes")
    _add_route_columns("version_room_routes")
    _add_route_columns("group_version_routes")
    _add_route_columns("user_version_routes")

    op.add_column(
        "support_groups",
        sa.Column(
            "notify_on_assignment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.add_column(
        "bot_issue_state",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column("group_reminder_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column("personal_reminder_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bot_issue_state",
        sa.Column(
            "reminder_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO bot_issue_journal_cursor (issue_id, last_journal_id, updated_at)
            SELECT issue_id, MAX(last_journal_id), now()
            FROM bot_issue_state
            WHERE last_journal_id IS NOT NULL
            GROUP BY issue_id
            ON CONFLICT (issue_id) DO UPDATE SET
                last_journal_id = GREATEST(
                    bot_issue_journal_cursor.last_journal_id,
                    EXCLUDED.last_journal_id
                ),
                updated_at = now()
            """
        )
    )

    _migrate_notification_templates_from_cycle_settings()
    _seed_cycle_settings_v2()


def downgrade() -> None:
    op.drop_column("bot_issue_state", "reminder_count")
    op.drop_column("bot_issue_state", "personal_reminder_due_at")
    op.drop_column("bot_issue_state", "group_reminder_due_at")
    op.drop_column("bot_issue_state", "status_changed_at")

    op.drop_column("support_groups", "notify_on_assignment")

    _drop_route_columns("user_version_routes")
    _drop_route_columns("group_version_routes")
    _drop_route_columns("version_room_routes")
    _drop_route_columns("status_room_routes")

    op.drop_table("notification_templates")
    op.drop_index("ix_bot_watcher_cache_issue_id", table_name="bot_watcher_cache")
    op.drop_table("bot_watcher_cache")
    op.drop_index("ix_pending_digests_user_created", table_name="pending_digests")
    op.drop_table("pending_digests")
    op.drop_table("bot_issue_journal_cursor")


def _add_route_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        table,
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        table,
        sa.Column(
            "notify_on_assignment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def _drop_route_columns(table: str) -> None:
    op.drop_column(table, "notify_on_assignment")
    op.drop_column(table, "sort_order")
    op.drop_column(table, "priority")


def _migrate_notification_templates_from_cycle_settings() -> None:
    bind = op.get_bind()

    def _get(key: str) -> str:
        row = bind.execute(text("SELECT value FROM cycle_settings WHERE key = :k"), {"k": key}).fetchone()
        if row and row[0]:
            return str(row[0]).strip()
        return ""

    tpl_new_html = _get("NOTIFY_TEMPLATE_HTML_NEW")
    tpl_new_plain = _get("NOTIFY_TEMPLATE_PLAIN_NEW")

    tpl_rem_html = _get("NOTIFY_TEMPLATE_HTML_REMINDER") or _get("NOTIFY_TEMPLATE_HTML_OVERDUE")
    tpl_rem_plain = _get("NOTIFY_TEMPLATE_PLAIN_REMINDER") or _get("NOTIFY_TEMPLATE_PLAIN_OVERDUE")

    order_change = [
        "NOTIFY_TEMPLATE_HTML_STATUS_CHANGE",
        "NOTIFY_TEMPLATE_HTML_ISSUE_UPDATED",
        "NOTIFY_TEMPLATE_HTML_INFO",
        "NOTIFY_TEMPLATE_HTML_REOPENED",
        "NOTIFY_TEMPLATE_HTML_OVERDUE",
    ]
    tpl_change_html = ""
    for k in order_change:
        tpl_change_html = _get(k)
        if tpl_change_html:
            break
    tpl_change_plain = ""
    for k in [x.replace("HTML", "PLAIN") for x in order_change]:
        tpl_change_plain = _get(k)
        if tpl_change_plain:
            break

    rows = [
        ("tpl_new_issue", tpl_new_html or None, tpl_new_plain or None),
        ("tpl_task_change", tpl_change_html or None, tpl_change_plain or None),
        ("tpl_reminder", tpl_rem_html or None, tpl_rem_plain or None),
    ]
    for name, html, plain in rows:
        if not html and not plain:
            continue
        bind.execute(
            text(
                """
                INSERT INTO notification_templates (name, body_html, body_plain, updated_at)
                SELECT :name, :html, :plain, now()
                WHERE NOT EXISTS (SELECT 1 FROM notification_templates t WHERE t.name = :name)
                """
            ),
            {"name": name, "html": html, "plain": plain},
        )


def _seed_cycle_settings_v2() -> None:
    bind = op.get_bind()
    seeds = [
        ("LAST_ISSUES_POLL_AT", "", "ISO-8601 UTC watermark for global issue poll"),
        ("MAX_ISSUES_PER_TICK", "50", "Max issues per phase-A response page"),
        ("MAX_PAGES_PER_TICK", "3", "Max Redmine API pages per tick for phase A"),
        ("WATCHER_CACHE_REFRESH_EVERY_N_TICKS", "10", "Refresh watcher cache full pass every N ticks"),
        ("DEFAULT_REMINDER_INTERVAL", "14400", "Default reminder interval seconds"),
        ("MAX_REMINDERS", "3", "Max reminder sends before stop"),
        ("DLQ_BATCH_SIZE", "10", "DLQ retry batch size per tick"),
        ("MAX_DLQ_RETRIES", "5", "Max DLQ retries before drop"),
        ("DRAIN_MAX_USERS_PER_TICK", "5", "Max users to drain pending_digests per tick"),
        ("MATRIX_MAX_RPS", "5", "Matrix client max sends per second cap"),
        ("JOURNAL_ENGINE_ENABLED", "0", "1=journal v2 engine, 0=legacy processor"),
    ]
    for key, value, desc in seeds:
        bind.execute(
            text(
                """
                INSERT INTO cycle_settings (key, value, description)
                VALUES (:key, :value, :desc)
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "value": value, "desc": desc},
        )
