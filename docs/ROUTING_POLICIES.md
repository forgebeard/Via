# Маршрутизация уведомлений (rules-only)

Политики в БД — единственный путь выбора Matrix-комнат для журнальных уведомлений. Legacy-таблицы статус/версия→комната удалены миграцией `0011_drop_legacy_routing`.

---

## Часть A. Источники правды в runtime

### `fetch_runtime_config` → бот

| Источник | Что попадает в ответ [`fetch_runtime_config`](../src/database/load_config.py) |
|----------|------------------|
| `SupportGroup` | Элементы `GROUPS` (профиль комнаты, фильтры `notify` / `versions` / `priorities`). |
| `RoutingPolicy` + оси (`routing_policy_statuses`, …) | `routes_config["routing_policies"]` — условия по задаче и `recipient_modes`; см. [`routing.py`](../src/bot/routing.py) `resolve_policy_target_rooms`. |

`fetch_runtime_config` возвращает `(USERS, GROUPS, routes_config)` без плоских мап.

### Сопоставление журнала с политиками

В [`handle_journal_entry`](../src/bot/journal_handlers.py) в `resolve_policy_target_rooms` передаётся **`journal_action_kind_for_routing`**: при ровно **одной** записи журнала в задаче — **`created`**; иначе — [`infer_event_type`](../src/bot/journal_handlers.py). Тексты шаблонов строятся из `infer_event_type` и контекста; ключ политики может отличаться.

### Потребители

| Данные | Потребители |
|--------|-------------|
| `routes_config["routing_policies"]` | [`resolve_policy_target_rooms`](../src/bot/routing.py) — выбор комнат для журнала. |
| `USERS` / `GROUPS` | `match_rooms`, `should_notify`, `issue_matches_cfg`. |

---

## Часть B. Runbook и проверки

### Ввод в эксплуатацию

1. `alembic upgrade head`.
2. `onboarding#rules`: policy с действием (`created` / `updated`), условиями по задаче, режимами получателей.
3. Стабильность по логам: `routing_no_match`, `routing_empty_target`.

### Чеклист

- `routing_no_match` — только для кейсов без подходящей policy.
- `routing_empty_target` — условия задачи выполнены, но получатели отфильтрованы (`should_notify` / `issue_matches_cfg`).
- Одно событие может идти в несколько комнат; дедуп по `room_id` в роутинге; для `new` / `issue_updated` — доп. дедуп на пару `issue+room+type`.
- CRUD policy отвергает невалидные FK и policy без `action_kind`.
- Для `updated` автор журнала не получает персональное уведомление; групповые каналы не подавляются.

### Rollback (операционно)

1. Отключить или поправить policy в админке.
2. При необходимости перезапустить бота.
3. Schema rollback через `alembic downgrade` — только осознанно.

### Pre-deploy (как ориентир)

Команды и полный набор — в CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) и [docs/index.md](index.md). Перед релизом политик — ручной smoke `onboarding#rules`.

### Связь с очисткой БД

Индексы под batched `DELETE` ретеншна (`bot_watcher_cache`, `bot_issue_dedup_state`, колонки `bot_issue_state`) — миграции `0012`, `0014`; код — [`db_retention.py`](../src/bot/db_retention.py). Подробности реализации смотреть в `alembic/versions/`, не в отдельном «continuation»-документе.
