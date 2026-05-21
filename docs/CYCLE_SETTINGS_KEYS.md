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

| `JOURNAL_SCOPE_MODE` | [`journal_pipeline.py`](../src/bot/journal_pipeline.py) | Границы запроса Phase A к Redmine: `all` — глобальный опрос; `projects` — объединение опросов по `JOURNAL_PROJECT_IDS`; `narrow` — устаревшее имя, то же intake что у `all` (единый required-contract). Невалидное значение → `all`. Фильтр по исполнителю бота / watcher cache на Phase A не применяется. |
| `JOURNAL_PROJECT_IDS` | [`journal_pipeline.py`](../src/bot/journal_pipeline.py) | JSON-массив Redmine `project_id` для режима `projects`; при пустом списке при `JOURNAL_SCOPE_MODE=projects` выполняется тот же глобальный опрос, что и для `all`. |

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

Этот документ фиксирует фактические чтения из кода. Изменения ключей делать только после синхронизации с [JOURNAL_PIPELINE.md](JOURNAL_PIPELINE.md) и смежной настройкой маршрутизации ([ROUTING_POLICIES.md](ROUTING_POLICIES.md)).

Начальные значения **`JOURNAL_SCOPE_MODE` = `all`** и **`JOURNAL_PROJECT_IDS` = `[]`** (idempotent, только при отсутствии строк) задаёт миграция Alembic **0015** [`a8f9e0d1c2b3`](../alembic/versions/a8f9e0d1c2b3_0015_journal_scope_seed.py). Ключи также входят в `CYCLE_SETTINGS_RECOGNIZED_KEYS` ([`cycle_settings_known.py`](../src/database/cycle_settings_known.py)), чтобы очистки «неразрешённых» строк в `cycle_settings` их не удаляли.
