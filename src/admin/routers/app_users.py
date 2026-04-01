"""Учётные записи операторов админки (BotAppUser)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.constants import COOKIE_SECURE, CSRF_COOKIE_NAME
from admin.csrf import ensure_csrf as _ensure_csrf, verify_csrf as _verify_csrf
from admin.runtime import logger
from admin.templates_env import templates
from database.models import BotAppUser, BotSession
from database.session import get_session
from mail import mask_email
from security import hash_password, validate_password_policy

router = APIRouter()


@router.get("/app-users", response_class=HTMLResponse)
async def app_users_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    rows = await session.execute(select(BotAppUser).order_by(BotAppUser.email))
    users = list(rows.scalars().all())
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "app_users.html",
        {"users": users, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return resp


@router.post("/app-users/{user_id}/reset-password-admin")
async def app_user_reset_password_admin(
    request: Request,
    user_id: str,
    new_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    current = getattr(request.state, "current_user", None)
    if not current or getattr(current, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    uid = uuid.UUID(user_id)
    q = await session.execute(select(BotAppUser).where(BotAppUser.id == uid))
    target = q.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Пользователь не найден")
    ok, reason = validate_password_policy(new_password, email=target.email)
    if not ok:
        raise HTTPException(400, reason)
    target.password_hash = hash_password(new_password)
    target.session_version = (target.session_version or 1) + 1
    await session.execute(delete(BotSession).where(BotSession.user_id == target.id))
    logger.info(
        "admin_password_reset target=%s actor=%s",
        mask_email(target.email),
        mask_email(current.email),
    )
    return RedirectResponse("/app-users", status_code=303)
