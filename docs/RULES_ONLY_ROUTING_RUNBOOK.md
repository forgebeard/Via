# Routing Runbook (rules-only + policy_v4)

## Cutover steps

1. Применить миграции: `alembic upgrade head`.
2. Открыть `onboarding#rules` и создать правило: действие (`created` / `updated`) + условия по задаче (статус/версия/приоритет). Явных списков пользователей/групп и выбора области адресатов нет — применяется объединение users + groups по атрибутам.
3. Убедиться, что legacy endpoints отключены (`/routes/status`, `/routes/version`, `/settings/routes/version` -> `410`).
4. Запуск в shadow-режиме: `ROUTING_ENGINE=legacy`, проверить `routing_shadow_diff` в логах.
5. Cutover: переключить `ROUTING_ENGINE=policy_v4` и перезапустить бота.
6. Проверить стабильность по логам/метрикам и no-match/empty-target событиям.

## Hard reset policy

- Старые one-room правила (`notification_routing_rules`) не переносятся автоматически.
- Policy v4 создаются заново в админке (hard reset).
- Shadow-режим нужен для проверки отличий `legacy_rooms` vs `policy_v4_rooms`.

## Verification checklist (policy v4)

- В логе есть `routing_shadow_diff` (только в legacy+shadow фазе).
- В логе есть `routing_no_match` только для действительно не покрытых policy кейсов.
- В логе есть `routing_empty_target`, если правило сработало по условиям задачи, но ни один адресат не прошёл фильтры подписок/атрибутов (`should_notify` / `issue_matches_cfg`).
- При `ROUTING_ENGINE=policy_v4` одно событие может отправляться в несколько комнат (dedup по room_id).
- CRUD policy отвергает невалидные FK и policy без действия (`action_kind`).
- Для `updated` автор journal не получает персональное уведомление (self-action suppression); группы при этом не исключаются.

## Rollback

1. Вернуть `ROUTING_ENGINE=legacy`.
2. Перезапустить бота.
3. Проверить, что `routing_shadow_diff` снова появляется и события отправляются legacy-контуром.
4. Schema rollback (`alembic downgrade`) выполнять только при отдельном решении, данные policy_v4 можно сохранить.

## Pre-deploy review gate

- [ ] `python -m ruff check src/`
- [ ] `python -m ruff format --check src/`
- [ ] `PYTHONPATH=src python -m mypy src/bot/logic.py src/bot/scheduler.py src/bot/routing.py src/matrix_send.py src/config.py src/database/state_repo.py src/database/load_config.py --explicit-package-bases`
- [ ] `python -m pytest tests/ -q --tb=short --ignore=tests/e2e`
- [ ] Ручной smoke `onboarding#rules` (действие + условия, без preview).
- [ ] Подтверждение feature flag сценария: `legacy -> policy_v4 -> legacy`.
