"""Контракт типов для позднего ``import admin.main`` из роутов (``_admin()``)."""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates


class AdminMainFacade(Protocol):
    DASHBOARD_PATH: str
    CSRF_COOKIE_NAME: str
    COOKIE_SECURE: bool
    templates: Jinja2Templates

    async def _load_statuses_catalog(self, session: AsyncSession) -> list[dict[str, str]]: ...

    def _ensure_csrf(self, request: Request) -> tuple[str, bool]: ...

    def _verify_csrf(self, request: Request, token: str) -> None: ...

    def _top_timezone_options(self) -> list[str]: ...

    def _standard_timezone_options(self) -> list[str]: ...

    def _timezone_labels(self, options: list[str]) -> dict[str, str]: ...

    def _matrix_bot_mxid(self) -> str: ...

    def _status_preset(
        self, notify: list[Any] | None, default_keys: list[str] | None = None
    ) -> str: ...

    def _parse_work_hours_range(self, value: str) -> tuple[str, str]: ...

    def _normalize_notify(
        self, values: list[str] | None, allowed_keys: list[str] | None = None
    ) -> list[str]: ...

    def _parse_notify(self, raw: str) -> list[Any]: ...

    def _parse_work_days(self, raw: str) -> list[int] | None: ...

    async def _maybe_log_admin_crud(
        self,
        session: AsyncSession,
        request_actor: Any,
        entity_type: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> None: ...
