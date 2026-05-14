"""Разрешённые ключи `cycle_settings`: читаются кодом, пишутся ботом или зарезервированы."""

from __future__ import annotations

# Читаются `main` / hot reload / `journal_tick` / журнальный пайплайн — см. docs/CYCLE_SETTINGS_KEYS.md.
# Резерв `DAILY_REPORT_*`: следующая итерация утреннего отчёта (см. доки).
CYCLE_SETTINGS_RECOGNIZED_KEYS: frozenset[str] = frozenset(
    {
        "BOT_LEASE_TTL_SECONDS",
        "BOT_TIMEZONE",
        "CHECK_INTERVAL",
        "CONTRACT_AUDIT_SAMPLE_LIMIT",
        "CONTRACT_AUDIT_VERBOSE",
        "DLQ_BATCH_SIZE",
        "DAILY_REPORT_ENABLED",
        "DAILY_REPORT_HOUR",
        "DAILY_REPORT_MINUTE",
        "JOURNAL_PROJECT_IDS",
        "JOURNAL_SCOPE_MODE",
        "LAST_ISSUES_POLL_AT",
        "MATRIX_DEVICE_ID",
        "MAX_ISSUES_PER_TICK",
        "MAX_PAGES_PER_TICK",
        "WATCHER_CACHE_REFRESH_EVERY_N_TICKS",
    }
)
