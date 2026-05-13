# Routing Runbook (rules-only)

## Cutover steps

1. Применить миграции: `alembic upgrade head`.
2. Открыть `onboarding#rules` и создать/обновить policy: действие (`created` / `updated`) + условия по задаче (статус/версия/приоритет) + режимы получателей.
3. Проверить стабильность по логам/метрикам и событиям `routing_no_match` / `routing_empty_target`.

## Hard reset policy

- Таблица `notification_routing_rules` не используется ботом для отправки журналов.
- Актуальный путь доставки журналов: `routing_policies` + пересечение профиля получателя.

## Verification checklist (policy v4)

- В логе есть `routing_no_match` только для действительно не покрытых policy кейсов.
- В логе есть `routing_empty_target`, если правило сработало по условиям задачи, но ни один адресат не прошёл фильтры подписок/атрибутов (`should_notify` / `issue_matches_cfg`).
- Одно событие может отправляться в несколько комнат (dedup по room_id в роутинге).
- Для `new` / `issue_updated` действует дополнительный дедуп по осям задачи на пару `issue+room+type`.
- CRUD policy отвергает невалидные FK и policy без действия (`action_kind`).
- Для `updated` автор journal не получает персональное уведомление (self-action suppression); группы при этом не исключаются.

## Rollback

1. Отключить/исправить проблемные policy в админке (`onboarding#rules`).
2. Перезапустить бота (если требуется по инфраструктуре).
3. Проверить логи `routing_no_match` / `routing_empty_target` и факт доставки.
4. Schema rollback (`alembic downgrade`) выполнять только при отдельном решении.

## Pre-deploy review gate

- [ ] `python -m ruff check src/`
- [ ] `python -m ruff format --check src/`
- [ ] `PYTHONPATH=src python -m mypy src/bot/logic.py src/bot/scheduler.py src/bot/routing.py src/matrix_send.py src/config.py src/database/state_repo.py src/database/load_config.py --explicit-package-bases`
- [ ] `python -m pytest tests/ -q --tb=short --ignore=tests/e2e`
- [ ] Ручной smoke `onboarding#rules` (действие + условия, без preview).
- [ ] Проверка, что старый `ROUTING_ENGINE` нигде не используется для runtime-доставки.
