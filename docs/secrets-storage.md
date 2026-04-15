```markdown
# Хранение секретов

Описание того, как Via хранит и защищает чувствительные данные.

## Что считается секретом

| Секрет | Где используется |
|--------|-----------------|
| `POSTGRES_PASSWORD` | Подключение к БД |
| `APP_MASTER_KEY` | Шифрование токенов Redmine и Matrix в БД |
| `REDMINE_API_KEY` | Доступ к Redmine REST API |
| `MATRIX_ACCESS_TOKEN` | Доступ к Matrix Homeserver |
| `SESSION_SECRET` | Подпись cookie сессий админки |

## Уровни защиты

### 1. Шифрование в БД (AES-256-GCM)

Токены Redmine и Matrix хранятся в таблице `app_settings` **зашифрованными**. Ключ — `APP_MASTER_KEY`.

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

> ⚠️ Смена ключа требует перешифрования данных в `app_settings`.

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
```