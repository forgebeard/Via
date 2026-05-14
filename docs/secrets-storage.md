# Хранение секретов

Описание того, как Via хранит и защищает чувствительные данные.

## Что считается секретом

| Секрет | Где используется |
|--------|-----------------|
| `POSTGRES_PASSWORD` | Подключение к БД |
| `APP_MASTER_KEY` | Шифрование токенов Redmine и Matrix в БД (`app_secrets`) |
| `REDMINE_API_KEY` | Доступ к Redmine REST API |
| `MATRIX_ACCESS_TOKEN` | Доступ к Matrix Homeserver |
| `SESSION_SECRET` | Подпись cookie сессий админки |

## Уровни защиты

### 1. Шифрование в БД (AES-256-GCM)

Токены Redmine и Matrix хранятся в таблице **`app_secrets`** зашифрованными. Ключ — `APP_MASTER_KEY`.

- Алгоритм: AES-256-GCM (аутентифицированное шифрование).
- Каждое значение шифруется с уникальным nonce.
- Без `APP_MASTER_KEY` расшифровать данные невозможно.

### 2. Хеширование паролей (Argon2id)

Пароли администраторов панели хешируются через **Argon2id** и никогда не хранятся в открытом виде.

### 3. Хранение `APP_MASTER_KEY`

**Вариант A — `.env` (по умолчанию):**

`deploy.sh` генерирует ключ автоматически и записывает в `.env`. Подходит для single-server установок.

```
APP_MASTER_KEY=base64:абвгд...==
```

**Вариант B — Docker secret (рекомендуется для production):**

1. Создайте секрет:
   ```bash
   echo "base64:абвгд...==" | docker secret create app_master_key -
   ```

2. В `docker-compose.yml`:
   ```yaml
   services:
     bot:
       secrets:
         - app_master_key
       environment:
         APP_MASTER_KEY_FILE: /run/secrets/app_master_key

   secrets:
     app_master_key:
       external: true
   ```

3. Удалите `APP_MASTER_KEY` из `.env`.

Приложение проверяет `APP_MASTER_KEY_FILE` первым — если файл существует, значение из `.env` игнорируется.

## Ротация `APP_MASTER_KEY`

Смена ключа требует перешифрования данных в `app_secrets`.

1. Сделайте бэкап БД.
2. Запустите скрипт ротации:
   ```bash
   docker compose exec admin python scripts/rotate_master_key.py \
     --old-key "base64:старый_ключ" \
     --new-key "base64:новый_ключ"
   ```
3. Обновите `APP_MASTER_KEY` в `.env` (или Docker secret).
4. Перезапустите сервисы: `docker compose restart bot admin`.

## Рекомендации

- **Не коммитьте `.env`** — он в `.gitignore`.
- **Бэкапьте `.env`** отдельно от кода, в защищённом хранилище.
- **Ограничьте доступ:** `chmod 600 .env`.
- **Для production** используйте Docker secrets (вариант B).
- **При компрометации** `APP_MASTER_KEY` — выполните ротацию и смените токены Redmine / Matrix.

## Имена ключей в `app_secrets`

Не удалять ключи без проверки: они нужны onboarding, боту и синхронизации каталогов.

### Обязательные для интеграции (onboarding; `REQUIRED_SECRET_NAMES` в [`helpers_ext.py`](../src/admin/helpers_ext.py))

- `REDMINE_URL`, `REDMINE_API_KEY`
- `MATRIX_HOMESERVER`, `MATRIX_ACCESS_TOKEN`, `MATRIX_USER_ID`

### Ожидание `bot.main` при bootstrap

Включая необязательный URL портала: `REDMINE_URL`, `REDMINE_API_KEY`, `PORTAL_BASE_URL`, `MATRIX_HOMESERVER`, `MATRIX_ACCESS_TOKEN`, `MATRIX_USER_ID`.  
`PORTAL_BASE_URL` в onboarding может быть пустым («нет override»).

### Системные имена админки (не в матрице onboarding)

Из [`helpers.py`](../src/admin/helpers.py):

- `__service_timezone` (`SERVICE_TIMEZONE_SECRET`)
- `__catalog_notify`, `__catalog_versions` — опрос каталогов Redmine

Управление: `/secrets` и onboarding. Удаление неиспользуемых имён — после аудита вызовов `_load_secret_plain` и веток onboarding.
