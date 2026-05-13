"""Глобальное состояние конфигурации бота.

Заполняется из main.py при старте (загрузка из БД).
Используется журнальным движком, scheduler.py и горячей перезагрузкой конфигурации.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.catalogs import BotCatalogs

# Пользователи бота (загружаются из БД)
USERS: list[dict] = []

# Группы бота (загружаются из БД)
GROUPS: list[dict] = []

# Расширенные маршруты для журнального движка (из load_config.fetch_runtime_config)
ROUTING: dict[str, Any] | None = None

# Справочники из БД (заполняется при старте)
CATALOGS: BotCatalogs | None = None
