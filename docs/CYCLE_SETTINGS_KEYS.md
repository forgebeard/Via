# Cycle Settings Keys

Сводка ключей `cycle_settings`, которые реально читаются runtime-кодом.

## Ключи, используемые в коде

| Ключ | Где читается | Назначение |
|------|--------------|------------|
| `CHECK_INTERVAL` | `bot/main.py`, `bot/config_hot_reload.py`, `bot/journal_tick.py` | Интервал основного цикла |
| `BOT_LEASE_TTL_SECONDS` | `bot/main.py`, `bot/config_hot_reload.py` | TTL lease координации |
| `BOT_TIMEZONE` | `bot/main.py`, `bot/config_hot_reload.py`, `admin/routes/settings.py` | Таймзона бота |
| `MATRIX_DEVICE_ID` | `bot/main.py`, `bot/config_hot_reload.py` | Device ID Matrix-клиента |
| `MAX_ISSUES_PER_TICK` | `bot/journal_tick.py` | Ограничение фазы A |
| `MAX_PAGES_PER_TICK` | `bot/journal_tick.py` | Ограничение страниц фазы A |
| `WATCHER_CACHE_REFRESH_EVERY_N_TICKS` | `bot/journal_tick.py` | Частота refresh watcher cache |
| `DLQ_BATCH_SIZE` | `bot/journal_tick.py` | Batch size DLQ retry |

## Deprecated / неиспользуемые ключи

| Ключ | Статус |
|------|--------|
| `JOURNAL_ENGINE_ENABLED` | В актуальном `src/` не читается. Исторический маркер из legacy-доков; не переключает кодовые ветки. |
| `REMINDER_AFTER` | Legacy-ключ, в текущем контуре журнала не используется для отправки reminder. |
| `GROUP_REPEAT_SECONDS` | Legacy-ключ, в текущем контуре журнала не используется. |
| `DRAIN_MAX_USERS_PER_TICK` | Исторический ключ digest-drain; digest-очередь отключена. |
| `MAX_REMINDERS` / `DEFAULT_REMINDER_INTERVAL` | Исторические ключи старого reminder_service. Следующая итерация rules-reminder будет использовать отдельные policy-настройки. |
| `DAILY_REPORT_*` | Ключи зарезервированы под следующую итерацию daily-report (таймзоны/точное время); текущий журнальный тик их не читает. |

## Примечание

Этот документ фиксирует фактические чтения из кода. Изменения ключей делать только после синхронизации с [docs/TZ_BOT_V2_IMPLEMENTATION.md](TZ_BOT_V2_IMPLEMENTATION.md) и [docs/JOURNAL_ENGINE_AND_SENDER.md](JOURNAL_ENGINE_AND_SENDER.md).
