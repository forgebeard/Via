# Документация Via

Исторические снимки и устаревшие ТЗ удалены из репозитория; при необходимости ищите в **истории git** по удалённым путям `docs/archive/`.

## Для операторов

| Документ | Описание |
|----------|----------|
| [README.md](../README.md) | Обзор проекта, быстрый старт |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Развёртывание (RHEL/Alma/Rocky), Docker |
| [ADMINISTRATOR_GUIDE.md](ADMINISTRATOR_GUIDE.md) | Панель, первый вход, troubleshooting |
| [DAY_ZERO_EXTENDED.md](DAY_ZERO_EXTENDED.md) | Сценарии: кнопка в UI → таблицы БД → бот |
| [rollback-runbook.md](rollback-runbook.md) | Аварийный откат |
| [AUDIT_LOGGING.md](AUDIT_LOGGING.md) | Логи и аудит панели |
| [secrets-storage.md](secrets-storage.md) | Секреты, `APP_MASTER_KEY`, имена в `app_secrets` |

## Для разработчиков

| Документ | Описание |
|----------|----------|
| [ADMIN_DB_BOT_AUDIT.md](ADMIN_DB_BOT_AUDIT.md) | Матрица UI → Postgres → бот; удаление данных; env |
| [JOURNAL_PIPELINE.md](JOURNAL_PIPELINE.md) | Планировщик, `run_journal_tick`, фазы A/B, DLQ |
| [ROUTING_POLICIES.md](ROUTING_POLICIES.md) | Rules-only: `fetch_runtime_config`, политики, runbook, связь с ретеншном |
| [notification_template_variables.md](notification_template_variables.md) | Поля Jinja `tpl_*`, точки вызова рендера |
| [MATRIX_NOTIFICATION_V5.md](MATRIX_NOTIFICATION_V5.md) | Контракт карточки v5, dedup, txn_id |
| [TEMPLATES_UNIFIED_HISTORY.md](TEMPLATES_UNIFIED_HISTORY.md) | История перехода на единый контур шаблонов |
| [CYCLE_SETTINGS_KEYS.md](CYCLE_SETTINGS_KEYS.md) | Ключи `cycle_settings` |
| [RUFF_BACKLOG.md](RUFF_BACKLOG.md) | Кратко про остаточный долг ruff |
| [ui-smoke-checklist.md](ui-smoke-checklist.md) | Ручной smoke UI перед merge |

## Служебное

| Путь | Описание |
|------|----------|
| [sql/redmine_catalog_unused_in_policies.sql](sql/redmine_catalog_unused_in_policies.sql) | Диагностический SQL (Postgres) |

## Перед продом (верификация)

Команды из корня репозитория (см. [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)):

1. `alembic upgrade head`
2. `python -m ruff check src/` и `python -m ruff format --check src/` (автофиксы: `ruff check src/ --fix`, `ruff format src/` — см. [RUFF_BACKLOG.md](RUFF_BACKLOG.md))
3. `python -m pytest tests/ -q --tb=short --ignore=tests/e2e`
4. Опционально: `python -m pip_audit -r requirements.txt`
5. В индексе git не должно быть артефактов: `git ls-files | rg '\.log$|\.coverage|\.pytest_cache'` — пусто; см. [`.gitignore`](../.gitignore)

Конфигурация: [.env.example](../.env.example).
