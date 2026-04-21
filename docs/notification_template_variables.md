# Переменные шаблонов уведомлений Matrix (`tpl_*`)

Шаблоны хранятся в таблице `notification_templates`, дефолтное тело — в `templates/bot/tpl_*.html.j2`. Контекст собирается в коде бота или админ-превью (`preview_issue_context_demo`, `_preview_context_for` в `notification_templates`).

Общее для issue-шаблонов (`tpl_new_issue`, `tpl_task_change`, `tpl_reminder`): функция `build_issue_context` в [`src/bot/template_context.py`](../src/bot/template_context.py) задаёт базовые поля; вызовы в [`sender.py`](../src/bot/sender.py) / [`journal_handlers.py`](../src/bot/journal_handlers.py) / [`reminder_service.py`](../src/bot/reminder_service.py) дополняют `emoji`, `title`, `event_type`, `extra_text`, `reminder_text` по сценарию.

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

Маршрут: типы `new`, `reopened` → [`EVENT_TO_TEMPLATE`](../src/bot/notification_template_routing.py).

Используются поля из общей таблицы выше; в заголовке выводится `emoji` и «Новая задача», затем блоки темы и статуса/приоритета.

---

## `tpl_task_change`

Маршрут: `info`, `overdue`, `issue_updated`, `status_change`.

Дополнительно: `title` (подпись рядом с префиксом), `event_type`, `extra_text`, а также структурированные поля журнала:

- `actor_name` — автор записи журнала.
- `changes` — список `{field, old, new}` (ограничение по длине, остаток в `extra_changes`).
- `journal_notes` — комментарий журнала.
- `status_from` — прежний статус при смене статуса.
- `assigned_from` — имя прежнего исполнителя (если найдено по `redmine_id`).

---

## `tpl_reminder`

Маршрут: `reminder`.

`reminder_text` — текст напоминания (например «Задача без движения»). Также доступны `reminder_count`, `max_reminders`, `elapsed_human`, `due_date`, `assignee_name`.

---

## `tpl_digest`

Контекст: `items` (и alias `digest_items`) — список агрегированных словарей (см. [`digest_service.py`](../src/bot/digest_service.py)).

Базовые поля элемента:

- `issue_id`, `subject`, `url`
- `events` (список типов событий)
- `changes` (список `{field, old, new}`)
- `comments` (список строк)
- `status_name`, `assigned_to`, `reminders_count`, `extra_changes`

---

## `tpl_dry_run`

Предпросмотр в админке: `issue_id`, `issue_url`, `subject`.

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
