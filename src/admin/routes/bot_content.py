"""Настройки контента бота из админки.

Тексты Matrix-уведомлений и утреннего отчёта — только через таблицу
``notification_templates`` и API ``/api/bot/notification-templates`` (tpl v2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_session

router = APIRouter(tags=["bot-content"])


def _admin() -> object:
    import admin.main as _m

    return _m


@router.get("/api/bot/content", response_class=JSONResponse)
async def bot_content_get(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    return {"ok": True, "settings": {}}


@router.post("/api/bot/content", response_class=JSONResponse)
async def bot_content_save(
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    admin._verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    del session
    return {"ok": True}
