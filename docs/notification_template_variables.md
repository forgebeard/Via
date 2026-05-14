# Переменные шаблонов уведомлений Matrix (`tpl_*`)

Шаблоны хранятся в таблице `notification_templates`, дефолтное тело — в `templates/bot/tpl_*.html.j2`. Контекст собирается в коде бота или админ-превью (`preview_issue_context_demo`, `_preview_context_for` в `notification_templates`).

## Контракт редактора (code-only)

- Вкладка `Уведомления` работает только в режиме `код + preview` для всех `tpl_*`.
- `tpl_dry_run` удалён из активного контура (реестр/API/UI); для тестовой проверки доставки используется `tpl_test_message`.
- Единый runtime-путь отправки Matrix использует `src/matrix_send.py` (legacy-модуль `src/matrix_client.py` удалён).
- Сохранение (`PUT /api/bot/notification-templates/{name}`) записывает `override_html` в БД.
- Сброс (`POST /api/bot/notification-templates/{name}/reset`) удаляет override и возвращает файловый default.
- Live-preview использует `POST /api/bot/notification-templates/preview`; при ошибке рендера UI показывает текст ошибки и не зависает в `loading`.

Общее для issue-шаблонов (`tpl_new_issue`, `tpl_task_change`, `tpl_reminder`): функция `build_issue_context` в [`src/bot/template_context.py`](../src/bot/template_context.py) задаёт базовые поля; вызовы в [`sender.py`](../src/bot/sender.py) / [`journal_handlers.py`](../src/bot/journal_handlers.py) дополняют `emoji`, `title`, `event_type`, `extra_text` по сценарию.

| Переменная | Описание |
|------------|----------|
| `issue_id` | Номер задачи Redmine |
| `issue_url` | Ссылка на задачу |
| `subject` | Тема задачи |
| `project_name` | Имя проекта задачи |
| `status` | Отображаемое имя статуса |
| `priority` | Отображаемое имя приоритета |
| `version` | Название версии (fixed_version) или пусто |
| `assignee_name` | Имя исполнителя или пустая строка |
| `description_excerpt` | Усечённый фрагмент описания задачи |
| `due_date` | Дедлайн (`str(issue.due_date)`) или пусто |
| `emoji` | Необязательный префикс в первой строке заголовка (строка, может быть пустой) |
| `title` | Подпись события в заголовке (`tpl_task_change`) |
| `event_type` | Тип события для строки «Тип: …» |
| `extra_text` | Дополнительный текст к событию |
| `reminder_text` | Текст блока напоминания (`tpl_reminder`) |
| `elapsed_human` | Человекочитаемый возраст последней активности |
| `reminder_count` | Номер текущего напоминания |
| `max_reminders` | Верхний лимит напоминаний |

---

## `tpl_new_issue`

Маршрут: тип `new` → [`EVENT_TO_TEMPLATE`](../src/bot/notification_template_routing.py) → `tpl_new_issue`.

Используются поля из общей таблицы выше; в заголовке выводится `emoji` и «Новая задача», затем блоки темы и статуса/приоритета.

---

## `tpl_task_change`

Маршрут: ключи `issue_updated`, `daily_report` (и иные, мапящиеся на этот tpl в [`EVENT_TO_TEMPLATE`](../src/bot/notification_template_routing.py)). Внутренний класс события журнала (`infer_event_type`: смена статуса, комментарий и т.д.) задаёт только поля контекста шаблона, а не отдельный ключ справочника `notification_types`.

Дополнительно: `title` (подпись рядом с префиксом), `event_type`, `extra_text`, а также структурированные поля журнала:

- `actor_name` — автор записи журнала.
- `changes` — список `{field, old, new}` (ограничение по длине, остаток в `extra_changes`).
- `journal_notes` — комментарий журнала.
- `status_from` — прежний статус при смене статуса.
- `assigned_from` — имя прежнего исполнителя (если найдено по `redmine_id`).
- `status_line` — строка для поля `Статус` в формате v5 (`old -> new` или текущее значение).
- `priority_line` — строка для поля `Приоритет` в формате v5.
- `version_line` — строка для поля `Версия` в формате v5.
- `assignee_line` — строка для поля `Исполнитель` в формате v5.

---

## `tpl_reminder`

Маршрут: `reminder`.

`extra_text` содержит текст напоминания (например «Задача без движения»). Также доступны `elapsed_human`, `due_date`, `assignee_name`.

---

## `tpl_test_message`

Тестовое сообщение из панели (`/users/test-message`, `/groups/test-message`) рендерится отдельным шаблоном.

| Переменная | Описание |
|------------|----------|
| `title` | Заголовок тестового сообщения (`Тестовое сообщение` / `Тестовое сообщение группы`) |
| `message` | Основной текст сообщения о проверке подключения |
| `sent_at` | Время отправки в формате `HH:MM:SS` |
| `timezone` | Таймзона сервиса, в которой вычислено `sent_at` |
| `scope` | Область теста: `user` или `group` |

---

## `tpl_daily_report`

Контекст формируется в [`build_daily_report_template_context`](../src/bot/scheduler.py) при отправке утреннего отчёта.

| Переменная | Описание |
|------------|----------|
| `report_date` | Дата строкой (формат `дд.мм.гггг` в текущей реализации) |
| `total_open` | Число открытых назначенных задач |
| `info_count` | Задачи в статусе «Информация предоставлена» |
| `overdue_count` | Просроченные по сроку |
| `info_items_html` | HTML (`<ul>…`) или пустая строка; в шаблоне через `\| safe` |
| `overdue_items_html` | HTML (`<ul>…`) или пустая строка; через `\| safe` |

---

## Безопасность

Поля с произвольным HTML из Redmine проходят экранирование при сборке контекста, кроме явно помеченных фрагментов списков в отчёте (`info_items_html` / `overdue_items_html`), собранных из уже экранированных частей в коде планировщика.

---

## Точки вызова рендера и контракт

### Решения по шаблонам

- **`tpl_test_message`** — только тестовая отправка из админки (`/users/test-message`, `/groups/test-message`).
- **`tpl_dry_run`** — вне runtime-контракта (реестр/API/шаблоны очищены миграциями).
- **`tpl_digest`** — удалён из продуктового контура.
- **`sandbox_accepts_context`** в [`template_loader.py`](../src/bot/template_loader.py) — парсинг дефолтного файла с диска; согласование с override из БД может отличаться от прод-рендера.
- Отправка Matrix — [`matrix_send.py`](../src/matrix_send.py).

### Где вызывается `render_named_template`

| Место | Шаблон | Контекст |
|-------|--------|----------|
| [`journal_handlers.journal_render_send_or_dlq`](../src/bot/journal_handlers.py) | `tpl_new_issue` / `tpl_task_change` / `tpl_reminder` | `build_issue_context` + `**extra` |
| [`scheduler.retry_dlq_notifications`](../src/bot/scheduler.py) | из `payload.template_name` | `payload.jinja_context` (снимок из DLQ) |

Предпросмотр в админке: [`notification_templates.py`](../src/admin/routes/notification_templates.py) — `SandboxedEnvironment.from_string(...).render(**ctx)`, не `render_named_template`. Контекст issue-синхронизирован с `build_issue_context` / `preview_issue_context_demo`.

`render_named_template` возвращает `tuple[str, str | None]` (HTML и plain); `None` для plain — fallback вызывающего.

### DLQ `needs_rerender`

`jinja_context` — JSON-safe снимок на момент события (см. [JOURNAL_PIPELINE.md](JOURNAL_PIPELINE.md)); сериализация и sanitize — [`journal_handlers.jinja_context_json_safe`](../src/bot/journal_handlers.py).
