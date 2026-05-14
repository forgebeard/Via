# Журнальный контур (pipeline)

Описание **актуального** кода: [`check_all_users`](../src/bot/scheduler.py) → [`run_journal_tick`](../src/bot/journal_tick.py) → фазы A/B в [`journal_pipeline.py`](../src/bot/journal_pipeline.py), обработка в [`journal_handlers.py`](../src/bot/journal_handlers.py), повтор DLQ в [`retry_dlq_notifications`](../src/bot/scheduler.py).

Legacy per-user polling (`check_user_issues` / `processor`) в репозитории отсутствует.

## Включение и флаги `cycle_settings`

Ключ **`JOURNAL_ENGINE_ENABLED`** в `cycle_settings` **не читается** в `src/` (ветвления по нему нет). Если строка есть в БД — это только операционная заметка; источник правды — вызовы в [`scheduler.py`](../src/bot/scheduler.py).

Охват Phase A задаётся ключами **`JOURNAL_SCOPE_MODE`** / **`JOURNAL_PROJECT_IDS`**; полный перечень читаемых ключей см. [CYCLE_SETTINGS_KEYS.md](CYCLE_SETTINGS_KEYS.md).

## Планировщик: один тик

1. [`check_all_users`](../src/bot/scheduler.py): `refresh_runtime_lists_from_db` → загрузка [`load_catalogs`](../src/bot/catalogs.py) → **`run_journal_tick`** → запись `runtime_status.json` (поле `journal_engine`: `v5_only`). Лог успешного цикла: «Журнальный цикл завершён» (при длительности выше порога — уровень `info`).

## `run_journal_tick`: порядок шагов

1. Каталоги и лимиты из `cycle_settings`: `MAX_ISSUES_PER_TICK`, `MAX_PAGES_PER_TICK`, `WATCHER_CACHE_REFRESH_EVERY_N_TICKS`, `DLQ_BATCH_SIZE`.
2. **Фаза A** — [`phase_a_candidates`](../src/bot/journal_pipeline.py): выборка кандидатов задач; [`persist_watermark`](../src/bot/journal_pipeline.py) по `LAST_ISSUES_POLL_AT` / максимуму `updated_on` среди полученных страниц.
3. **Периодический refresh кэша наблюдателей** (если `WATCHER_CACHE_REFRESH_EVERY_N_TICKS > 0` и номер тика кратен N): догрузка задач из множества наблюдаемых id, [`sync_watcher_cache_for_issue`](../src/bot/journal_pipeline.py), удаление устаревших строк кэша по порогу `max(24ч, 2 * N * CHECK_INTERVAL)`.
4. **По каждому кандидату**: [`reload_issue_with_journals`](../src/bot/journal_pipeline.py) → синхронизация watcher cache → новые журналы → [`handle_journal_entry`](../src/bot/journal_handlers.py) (маршрутизация, шаблоны `tpl_*`, при необходимости DLQ) → [`advance_cursor_after_journal`](../src/bot/journal_pipeline.py) и `commit`. Исполнитель для маршрутизации может отсутствовать (`assignee_cfg` optional).
5. После выхода из основной DB-сессии — **`retry_dlq_notifications`** с лимитом из `DLQ_BATCH_SIZE`.

Отдельного шага **digest drain** или **`process_reminders`** в `run_journal_tick` нет (контуры digest/reminder v1 в этом модуле не подключены).

### Водяной знак и курсор журнала

- **`LAST_ISSUES_POLL_AT`** — водяной знак глобального поллинга фазы A; продвигается по максимальному `updated_on` среди полученных страниц.
- **`bot_issue_journal_cursor.last_journal_id`** — по задаче: до какого `journal_id` обработано. При ошибке доставки/рендера типичный путь: DLQ + курсор вперёд; детали формата payload и политика «at-most-once» — в коде [`journal_render_send_or_dlq`](../src/bot/journal_handlers.py) и `retry_dlq_notifications`.

## Шаблоны и маршрутизация

- Именованные шаблоны `tpl_*` в БД (`notification_templates`) и файлах `templates/bot/`. См. [notification_template_variables.md](notification_template_variables.md), [TEMPLATES_UNIFIED_HISTORY.md](TEMPLATES_UNIFIED_HISTORY.md).
- Политики комнат: [`ROUTING_POLICIES.md`](ROUTING_POLICIES.md) и `fetch_runtime_config` → `routes_config["routing_policies"]`.

## Проверка на стенде

Убедиться по логам, что выполняется `run_journal_tick` (сообщение о завершении цикла), продвижение водяного знака и курсора на тестовой задаче; сломать шаблон в БД и проверить запись в `pending_notifications` / успешный retry после исправления.
