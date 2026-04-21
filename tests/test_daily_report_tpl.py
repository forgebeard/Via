"""Утренний отчёт: контекст Jinja для tpl_daily_report."""

from __future__ import annotations

from bot.scheduler import build_daily_report_template_context


def test_build_daily_report_template_context_contract() -> None:
    ctx = build_daily_report_template_context(
        report_date="15.04.2026",
        total_open=5,
        info_count=1,
        overdue_count=2,
        info_items_html="<ul><li>x</li></ul>",
        overdue_items_html="<p>y</p>",
    )
    assert ctx["report_date"] == "15.04.2026"
    assert ctx["total_open"] == 5
    assert ctx["info_count"] == 1
    assert ctx["overdue_count"] == 2
    assert ctx["info_items_html"] == "<ul><li>x</li></ul>"
    assert ctx["overdue_items_html"] == "<p>y</p>"
