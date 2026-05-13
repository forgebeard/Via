"""Безопасная запись в .env файл с file-locking.

Предотвращает race conditions при одновременной записи из нескольких
процессов/потоков (например, админка + init-скрипт).
"""

from __future__ import annotations

import fcntl
import logging
from pathlib import Path

logger = logging.getLogger("redmine_admin")

_ENV_FILE_PATH = Path("/app/.env")


def update_env_file_with_lock(updates: dict[str, str], env_path: Path | None = None) -> None:
    """Атомарно обновляет переменные в .env файле с использованием flock.

    - Блокирует файл на запись (fcntl.LOCK_EX).
    - Читает существующие строки, обновляет/добавляет ключи.
    - Записывает обратно и снимает блокировку.

    Если файл не существует — бросает RuntimeError.
    """
    target = env_path or _ENV_FILE_PATH
    if not target.exists():
        raise RuntimeError(f"{target} file not found")

    # Открываем файл для чтения+записи, блокируем
    with target.open("r+", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except OSError as e:
            logger.warning("Failed to lock %s: %s", target, e)
            # Fallback: пишем без блокировки (например, на FS без flock support)
            _update_in_memory_and_write(updates, target)
            return

        try:
            lines = f.read().splitlines()
            new_lines = []
            updated_keys = set()

            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        new_lines.append(f"{key}={updates[key]}")
                        updated_keys.add(key)
                        continue
                new_lines.append(line)

            # Добавляем новые ключи, которых не было в файле
            for key, value in updates.items():
                if key not in updated_keys:
                    new_lines.append(f"{key}={value}")

            # Перемещаем указатель в начало, усекаем, пишем
            f.seek(0)
            f.truncate()
            f.write("\n".join(new_lines) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _update_in_memory_and_write(updates: dict[str, str], target: Path) -> None:
    """Fallback: читаем файл в память, обновляем, пишем обратно (без flock)."""
    lines = target.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated_keys = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
