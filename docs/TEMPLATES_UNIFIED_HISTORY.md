# История: единый контур шаблонов Matrix (`tpl_*`)

Сводка **решений** и **миграции** со старого контура (`NOTIFY_TEMPLATE_*` в `cycle_settings`, `notification.html`) на таблицу `notification_templates` + файлы `templates/bot/tpl_*.html.j2`.

## Контекст (ADR)

Раньше тело сообщения собиралось несколькими путями. Цель — для `send_safe` / `build_matrix_message_content` использовать те же именованные шаблоны, что и админка. Legacy-ветки и переменные отката удалены.

### DLQ

В DLQ сохраняется готовый `payload` (`m.room.message`), собранный тем же кодом, что и успешная отправка. Вариант «только `template_name` + `jinja_context` в DLQ» не принят — меньше изменений в `dlq_repo` и retry.

### Утренний отчёт

Тип `daily_report` маппится на шаблон через [`EVENT_TO_TEMPLATE`](../src/bot/notification_template_routing.py) (сейчас — `tpl_task_change`, пока нет отдельного job/`tpl_daily_report`). Расписание — ключи `DAILY_REPORT_*` в `cycle_settings`, см. актуальные ревизии `alembic/versions/`.

### Релизный чеклист (вручную на стенде)

1. По каждому ключу из `EVENT_TO_TEMPLATE` (`new`, `reminder`, `issue_updated`, `daily_report`) — одно реальное сообщение в комнату; верстка и ссылка на задачу.
2. Изменить override `tpl_*` в админке без деплоя — повторная отправка того же типа с новым текстом.
3. Утренний отчёт — при включённом job проверить расписание.

Дополнительно: для `issue_updated` каноничный формат карточки v5 в `tpl_task_change`; в админке — code-only редактор, block-endpoints удалены (`404`). Превью: `POST /api/bot/notification-templates/preview`.

## Миграция для оператора (старые `NOTIFY_TEMPLATE_*`)

Раньше переопределения задавались ключами `NOTIFY_TEMPLATE_HTML_{TYPE}` / `NOTIFY_TEMPLATE_PLAIN_{TYPE}` в `cycle_settings` (`{TYPE}` в верхнем регистре: `NEW`, `ISSUE_UPDATED`, …).

**Что сделать**

1. Перенести текст в соответствующие шаблоны: `new` → `tpl_new_issue`; `issue_updated`, `daily_report` → `tpl_task_change`; `reminder` → `tpl_reminder`.
2. Проверить предпросмотр в админке.
3. Ключи `NOTIFY_TEMPLATE_*` в `cycle_settings` снимаются миграциями; API `/api/bot/content` этот JSON не хранит. Актуальные номера ревизий — в `alembic/versions/`.

Старый `notification.html` и чтение `NOTIFY_TEMPLATE_*` для Matrix из кода удалены; остаётся tpl v2.
