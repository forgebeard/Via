# План выноса админки из `admin_main.py` (неделя, внутренняя чистота)

## Сделано (день 1)

- Пакет `src/admin/`: `constants`, `templates_env`, `csrf`, `csp`, `lifespan`.
- Роутер `src/admin/routers/health.py`, подключение в `admin_main.py`.
- `admin_main.py` — реэкспорт `_admin_asset_version` / `_admin_csp_value` для существующих тестов.

## Дальше по дням

| День | Задача |
|------|--------|
| 2 | `src/admin/runtime.py`: логгер, `SimpleRateLimiter`, кэши; `session_logic.py`: `_has_admin`, `_integration_status`, `_runtime_status_from_file` |
| 3 | `src/admin/middleware/auth.py` — `AuthMiddleware`; в `admin_main` только `app.add_middleware` |
| 4 | Роутер `routers/auth.py` (login, setup, forgot/reset, logout, onboarding) |
| 5 | Роутер `routers/users.py` или `ops.py` + остальное порциями; финальный тонкий `admin_main` |

## Инварианты

- Два процесса (bot + admin), URL и поведение без регрессий.
- Rate limit — in-memory, одна реплика админки.
- Миграции только Alembic вперёд.
