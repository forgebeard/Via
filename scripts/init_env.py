#!/usr/bin/env python3
"""
Генерирует .env файл при первом запуске с случайными POSTGRES_PASSWORD и APP_MASTER_KEY.

Если .env уже существует — ничего не делает (идемпотентность).
При перегенерации (env var REGENERATE=1) создаёт новые credentials.

Использование:
  # Первый запуск (создаёт .env если его нет):
  python scripts/init_env.py

  # Перегенерация (создаёт новые credentials, перезаписывает .env):
  REGENERATE=1 python scripts/init_env.py
"""

import os
import secrets
from pathlib import Path

# Путь к .env файлу (в Docker: /app/.env, локально: ./env от корня проекта)
ENV_FILE = Path(os.getenv("ENV_FILE_PATH", "/app/.env"))


def generate_credentials() -> dict[str, str]:
    """Генерирует случайные credentials для БД и шифрования."""
    return {
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "APP_MASTER_KEY": secrets.token_hex(16),
    }


def parse_existing_env(env_file: Path) -> dict[str, str]:
    """Парсит существующий .env файл, сохраняя все переменные."""
    config = {}
    if not env_file.exists():
        return config

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def write_env_file(env_file: Path, config: dict[str, str]) -> None:
    """Записывает .env файл с комментариями и переменными."""
    lines = [
        "# =============================================================================",
        "# Автогенерировано при первом запуске (scripts/init_env.py)",
        "#",
        "# POSTGRES_PASSWORD — пароль для PostgreSQL (генерируется автоматически)",
        "# APP_MASTER_KEY — мастер-ключ для шифрования секретов в БД",
        "#",
        "# Все остальные параметры (Matrix, Redmine) настраиваются через GUI админки:",
        "# http://localhost:8080/onboarding",
        "# =============================================================================",
        "",
        f"POSTGRES_PASSWORD={config['POSTGRES_PASSWORD']}",
        f"APP_MASTER_KEY={config['APP_MASTER_KEY']}",
        "",
        "# Опционально: можно переопределить эти значения",
        "# POSTGRES_USER=bot",
        "# POSTGRES_DB=via",
        "# ADMIN_PORT=8080",
        "# BOT_TIMEZONE=Europe/Moscow",
        "",
    ]
    env_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    regenerate = os.getenv("REGENERATE", "").lower() in ("1", "true", "yes", "on")

    # Check if .env exists but has empty/placeholder values — treat as first run
    if ENV_FILE.exists() and not regenerate:
        existing = parse_existing_env(ENV_FILE)
        if existing.get("POSTGRES_PASSWORD") and existing.get("APP_MASTER_KEY"):
            print(f"[INIT] ✅ .env file already exists at {ENV_FILE}, skipping generation.")
            print("[INIT] To regenerate credentials, set REGENERATE=1 env variable.")
            return
        # File exists but values are missing/empty — regenerate
        print("[INIT] 🔄 .env exists but has missing values, regenerating...")
        regenerate = True

    credentials = generate_credentials()

    if ENV_FILE.exists() and regenerate:
        print("[INIT] 🔄 Regenerating credentials (existing .env will be overwritten)...")
    else:
        print(f"[INIT] 🚀 First run: generating .env file at {ENV_FILE}...")

    write_env_file(ENV_FILE, credentials)

    print("[INIT] ✅ .env file created successfully!")
    print(f"[INIT] 📝 POSTGRES_PASSWORD: {credentials['POSTGRES_PASSWORD']}")
    print(f"[INIT] 🔑 APP_MASTER_KEY: {credentials['APP_MASTER_KEY']}")
    print("[INIT] ⚠️  IMPORTANT: Save these credentials securely!")
    print("[INIT] 💡 You can view them later in the admin panel at /onboarding")

    if regenerate:
        print(
            "[INIT] 🔄 After regenerating, restart containers: docker compose restart postgres bot admin"
        )


if __name__ == "__main__":
    main()
