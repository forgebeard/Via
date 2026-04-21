"""tpl_daily_report: migrate DAILY_REPORT_* HTML/plain from cycle_settings; drop NOTIFY_TEMPLATE_*.

Revision ID: 0022_daily_report_tpl (≤32 символа для alembic_version.version_num)
Revises: 0021_journal_engine_v2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_daily_report_tpl"
down_revision: str | None = "0021_journal_engine_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _cycle_get(conn: sa.Connection, key: str) -> str:
    row = conn.execute(
        sa.text("SELECT value FROM cycle_settings WHERE key = :k"), {"k": key}
    ).fetchone()
    return (row[0] or "").strip() if row else ""


def _format_placeholders_to_jinja(html: str, plain: str) -> tuple[str, str]:
    """Грубая замена плейсхолдеров ``.format`` на Jinja для переноса в tpl_daily_report."""

    def conv(s: str) -> str:
        if not s:
            return ""
        r = s
        r = r.replace("{info_items_html}", "{{ info_items_html | safe }}")
        r = r.replace("{overdue_items_html}", "{{ overdue_items_html | safe }}")
        r = r.replace("{date}", "{{ report_date }}")
        r = r.replace("{total_open}", "{{ total_open }}")
        r = r.replace("{info_count}", "{{ info_count }}")
        r = r.replace("{overdue_count}", "{{ overdue_count }}")
        return r

    return conv(html), conv(plain)


def upgrade() -> None:
    conn = op.get_bind()
    assert conn is not None
    html_raw = _cycle_get(conn, "DAILY_REPORT_HTML_TEMPLATE")
    plain_raw = _cycle_get(conn, "DAILY_REPORT_PLAIN_TEMPLATE")
    html_j, plain_j = _format_placeholders_to_jinja(html_raw, plain_raw)

    tpl_row = conn.execute(
        sa.text("SELECT body_html, body_plain FROM notification_templates WHERE name = :n"),
        {"n": "tpl_daily_report"},
    ).fetchone()
    if tpl_row is None and (html_j or plain_j):
        conn.execute(
            sa.text(
                """
                INSERT INTO notification_templates (name, body_html, body_plain, updated_at)
                VALUES (:name, :html, :plain, now())
                """
            ),
            {"name": "tpl_daily_report", "html": html_j or None, "plain": plain_j or None},
        )
    elif tpl_row is not None and (html_j or plain_j):
        cur_h = (tpl_row[0] or "").strip()
        cur_p = (tpl_row[1] or "").strip()
        if not cur_h and html_j:
            conn.execute(
                sa.text(
                    "UPDATE notification_templates SET body_html = :h, updated_at = now() "
                    "WHERE name = :n AND (body_html IS NULL OR trim(body_html) = '')"
                ),
                {"h": html_j, "n": "tpl_daily_report"},
            )
        if not cur_p and plain_j:
            conn.execute(
                sa.text(
                    "UPDATE notification_templates SET body_plain = :p, updated_at = now() "
                    "WHERE name = :n AND (body_plain IS NULL OR trim(body_plain) = '')"
                ),
                {"p": plain_j, "n": "tpl_daily_report"},
            )

    conn.execute(
        sa.text(
            "DELETE FROM cycle_settings WHERE key IN "
            "('DAILY_REPORT_HTML_TEMPLATE', 'DAILY_REPORT_PLAIN_TEMPLATE')"
        )
    )
    conn.execute(
        sa.text("DELETE FROM cycle_settings WHERE key LIKE 'NOTIFY_TEMPLATE_%'")
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM notification_templates WHERE name = 'tpl_daily_report'")
    )
