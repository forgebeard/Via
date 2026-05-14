# Аудит: админка → БД → бот (этап 0 плана)

Дата: 2026-04-18. Цель: зафиксировать матрицу источников данных, разрывы с `.env` и сценарии удаления.

## Кратко: принцип admin / БД / бот

- **Эксплуатация:** оператор не обязан править код репозитория. Политика «кому, куда, с какими фильтрами», справочники, шаблоны, интервалы из UI, секреты в Postgres; бот подхватывает данные при старте и при hot reload (см. [ADMINISTRATOR_GUIDE.md](ADMINISTRATOR_GUIDE.md)).
- **Продукт:** смена семантики уведомлений и пайплайна — в коде `src/bot/` и релиз.
- **Инфраструктура:** `.env` / compose (`ADMIN_URL`, `BOT_INSTANCE_ID`, логи, часть таймингов без UI) — зона деплоя.

В SQL сознательно **не** живут: журнал страницы «События» (файл на диске), статус контейнера бота (Docker + при необходимости `runtime_status.json`).

Краткий чеклист после развёртывания: [ADMINISTRATOR_GUIDE.md](ADMINISTRATOR_GUIDE.md). Пошагово по кнопкам панели: [DAY_ZERO_EXTENDED.md](DAY_ZERO_EXTENDED.md). Деплой сервера: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

Часть интервалов по умолчанию в [`src/config.py`](../src/config.py) с перезаписью из БД в `main()`; параметры только в `.env` — см. комментарии `config.py` и гайд администратора (рестарт vs hot reload).

## 1. Матрица: экран / API админки → таблицы Postgres → что читает бот

| Область | Где в админке | Таблицы / хранилище | Как бот использует |
|--------|----------------|----------------------|---------------------|
| Интеграция Matrix + Redmine (URL, ключ, токены) | `/onboarding` ([`settings.onboarding_save`](../src/admin/routes/settings.py)), `/secrets` ([`secrets_save`](../src/admin/routes/secrets.py)) | `app_secrets` (`AppSecret`) | [`main.py`](../src/bot/main.py): ожидание всех имён `REDMINE_URL`, `REDMINE_API_KEY`, `MATRIX_HOMESERVER`, `MATRIX_ACCESS_TOKEN`, `MATRIX_USER_ID` |
| Сервисная таймзона (для админки при старте) | onboarding, секрет с именем `__service_timezone` (см. [`main.py`](../src/admin/main.py) `SERVICE_TIMEZONE_SECRET`) | `app_secrets` | Бот основную таймзону берёт из `cycle_settings` / каталогов после старта, не из этого ключа напрямую |
| Интервалы, таймзона бота; **Matrix device ID**; подготовка к daily-report | [`/onboarding`](../src/admin/routes/settings.py), API [`/api/bot/content`](../src/admin/routes/bot_content.py) | `cycle_settings` (`CycleSettings`); ключи в т.ч. `BOT_TIMEZONE`, `MATRIX_DEVICE_ID`, `DAILY_REPORT_ENABLED` / `HOUR` / `MINUTE` | [`load_catalogs`](../src/bot/catalogs.py) + [`fetch_cycle_settings`](../src/database/load_config.py) в [`main.py`](../src/bot/main.py) |
| Тексты Matrix-шаблонов (tpl v2) | вкладка «Уведомления» onboarding, API [`/api/bot/notification-templates`](../src/admin/routes/notification_templates.py) | `notification_templates` + файлы `templates/bot/tpl_*.html.j2` | [`render_named_template`](../src/bot/template_loader.py); `tpl_digest` удалён из продуктового контура |
| Пользователи бота | `/users` | `bot_users` (`BotUser`), опционально ключ в колонках ciphertext | [`fetch_runtime_config`](../src/database/load_config.py) |
| Группы поддержки | `/groups` | `support_groups` | [`fetch_runtime_config`](../src/database/load_config.py) → профиль группы в `GROUPS` |
| Правила маршрутизации журналов | `/onboarding#rules` ([`routing_rules.py`](../src/admin/routes/routing_rules.py)) | `routing_policies`, `routing_policy_statuses`, `routing_policy_versions`, `routing_policy_priorities` | `routes_config["routing_policies"]` → [`resolve_policy_target_rooms`](../src/bot/routing.py) |
| Справочники Redmine | каталог в админке [`catalog`](../src/admin/routes/catalog.py) | `redmine_statuses`, `redmine_versions`, `redmine_priorities`, `notification_types` | [`load_catalogs`](../src/bot/catalogs.py) |
| Аккаунты панели (логин) | `/app-users` и др. | `bot_app_users`, `bot_sessions`, … | Не используются ботом для рассылки |
| Очередь доставки Matrix (thin worker) | GET [`/api/bot/commands`](../src/admin/routes/bot_runtime.py), POST ack/error | `pending_notifications` (отдельной таблицы «команд» нет) | [`command_worker`](../src/bot/command_worker.py): pull из API; та же DLQ, что и retry в монолитном боте |

## 2. Что бот всё ещё берёт из окружения / [`config.py`](../src/config.py) (не из «мозга» БД)

### 2.1. Непосредственно в процессе бота (`src/bot/`)

| Переменная / источник | Назначение | Заметка |
|----------------------|------------|---------|
| `BOT_INSTANCE_ID` | UUID инстанса | Инфраструктура |
| `BOT_RUNTIME_STATUS_FILE` | путь к `runtime_status.json` | Инфраструктура |
| `ADMIN_URL` | HTTP к админке: pull-команды + ack/error | Инфраструктура; должен указывать на тот же «мозг» |

### 2.2. Через импорт [`config.py`](../src/config.py) (загрузка при старте модуля)

Пути логов (`LOG_*`), `MATRIX_DEVICE_ID`, retry Matrix (`MATRIX_RETRY_*`), `CHECK_INTERVAL` / `REMINDER_AFTER` / … как **дефолты до** перезаписи из БД в `main()`; `CONFIG_POLL_INTERVAL_SEC`, `COMMAND_POLL_INTERVAL_SEC`, `BOT_LEASE_TTL_SECONDS` — пока без UI в `cycle_settings` для части из них.

В [`config.py`](../src/config.py) имена `USERS` / `STATUS_ROOM_MAP` / `VERSION_ROOM_MAP` оставлены пустыми (не читаются из `.env`); источник правды — Postgres и `bot.main`. Периодическая подгрузка без рестарта: [`config_hot_reload.py`](../src/bot/config_hot_reload.py), env `BOT_HOT_RELOAD` / `BOT_HOT_RELOAD_INTERVAL_SEC`.

Фоновый **ретеншн** «мусорных» строк (DLQ, аудит CRUD, истёкшие сессии и токены, привязки Matrix, кэш наблюдателей, dedup журнала): ежедневно в планировщике бота ~03:12 в `BOT_TIMEZONE` — [`db_retention.py`](../src/bot/db_retention.py); горизонт и батчи: env `DB_RETENTION_JOBS_ENABLED` / `DB_RETENTION_DAYS` / `DB_RETENTION_BATCH_SIZE` / `DB_DLQ_WARN_ROWS` (см. `.env.example`); индексы под batched `DELETE` — миграции `0012_retention_indexes`, `0014_issue_state_drop_and_retention_more`. Краткая связка миграций с правилами маршрутизации и схемой — [ROUTING_POLICIES.md](ROUTING_POLICIES.md).

### 2.3. Риск рассинхрона

- **Смягчено:** единая функция `effective_bot_timezone_for_admin` ([`helpers_ext.py`](../src/admin/helpers_ext.py)) выставляет `BOT_TIMEZONE` при старте админки и после сохранения onboarding: приоритет `cycle_settings.BOT_TIMEZONE` → секрет `__service_timezone` → env. Сохранение формы onboarding дополнительно пишет `BOT_TIMEZONE` в `cycle_settings` и дублирует в `__service_timezone`.

## 3. Удаление в админке и целостность данных

### 3.1. Реализованные удаления (строки реально уходят из БД)

- **Пользователь бота** [`users_delete`](../src/admin/routes/users.py) / bulk-delete: `DELETE` из `bot_users`.
- **Группа** [`groups_delete`](../src/admin/routes/groups.py): удаление `support_groups`; у пользователей `group_id` → **SET NULL**.
- **Legacy маршруты** (`status_room_routes`, `version_room_routes`, per-user/group version routes) **сняты с схемы**; настройка доставки — только политики в onboarding.
- **Каталог** Redmine: [`catalog_*_delete`](../src/admin/routes/catalog.py) — `DELETE` строки справочника.

### 3.2. Пробелы и закрытые моменты

| Тема | Статус |
|------|--------|
| **Секреты** | Удаление строки `app_secrets` — POST [`/secrets/delete`](../src/admin/routes/secrets.py), кнопка в [`secrets.html`](../templates/admin/panel/secrets.html); аудит CRUD при включённом флаге. |
| **State / lease / DLQ при удалении пользователя** | При удалении [`bot_users`](../src/admin/routes/users.py) вызывается [`delete_runtime_data_for_redmine_user`](../src/database/user_runtime_cleanup.py): очистка `bot_issue_state`, `pending_notifications`, `bot_user_leases` по `user_redmine_id`. |
| **Не-SQL** | Журнал `/events` (файл), статус бота (Docker + при необходимости `runtime_status.json`) — по-прежнему вне таблиц конфигурации. |

### 3.3. Вывод

Для маршрутизации, каталога, секретов и удаления пользователя бота цепочка «UI → БД → согласованные данные» **приведена к ожидаемому виду** для перечисленного выше. Исключения — осознанные (файловый журнал, инфраструктурный статус). Принцип работы admin/БД/бот — в начале этого документа.

## 4. История заметок (аудит)

Ранее здесь был список «следующих задач»; часть пунктов выполнена (секреты, очистка при удалении пользователя, см. §3.2). Актуальные операционные шаги: [`ADMINISTRATOR_GUIDE.md`](ADMINISTRATOR_GUIDE.md).

---

*Документ можно обновлять по мере рефакторинга; ссылка на него в roadmap плана «admin = brain, bot = hands».*
