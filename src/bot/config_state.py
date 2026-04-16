"""Глобальное состояние конфигурации бота.

Заполняется из main.py при старте (загрузка из БД).
Используется processor.py и scheduler.py.
"""

from __future__ import annotations

# Пользователи бота (загружаются из БД)
USERS: list[dict] = []

# Маршрутизация: статус → Matrix room
STATUS_ROOM_MAP: dict[str, str] = {}

# Маршрутизация: версия → Matrix room (глобальный)
VERSION_ROOM_MAP: dict[str, str] = {}

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.catalogs import BotCatalogs

# ... существующие USERS, STATUS_ROOM_MAP, VERSION_ROOM_MAP ...

# ── Справочники из БД (заполняется при старте) ───────────────────────
CATALOGS: BotCatalogs | None = None