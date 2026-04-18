"""Me routes: /me/settings (user self-service)."""

from __future__ import annotations

import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotUser
from database.session import get_session

router = APIRouter(tags=["me"])


def _admin() -> object:
    """Late import to avoid circular dependency with main.py."""
    import admin.main as _m

    return _m


@router.get("/me/settings", response_class=HTMLResponse)
async def me_settings_get(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if getattr(user, "role", "") == "admin":
        return RedirectResponse(admin.DASHBOARD_PATH, status_code=303)

    redmine_id = getattr(user, "redmine_id", None)
    statuses_catalog = await admin._load_statuses_catalog(session)
    status_default_keys = [item["key"] for item in statuses_catalog]
    csrf_token, set_cookie = admin._ensure_csrf(request)
    if redmine_id is None:
        resp = admin.templates.TemplateResponse(
            request,
            "panel/my_settings.html",
            {
                "room": None,
                "status_json": '["all"]',
                "status_preset": "default",
                "status_selected": status_default_keys,
                "statuses_catalog": statuses_catalog,
                "work_hours": "",
                "work_hours_from": "",
                "work_hours_to": "",
                "timezone_name": os.getenv("BOT_TIMEZONE", "Europe/Moscow"),
                "timezone_top_options": admin._top_timezone_options(),
                "timezone_all_options": admin._standard_timezone_options(),
                "timezone_labels": admin._timezone_labels(admin._standard_timezone_options()),
                "work_days_json": "",
                "work_days_selected": [0, 1, 2, 3, 4],
                "dnd": False,
                "error": (
                    "Учётная запись в панели ещё не связана с Redmine. "
                    "Подписка на уведомления настраивается через бота в Matrix "
                    "или попросите администратора завести вас в разделе «Пользователи»."
                ),
                "matrix_bot_mxid": admin._matrix_bot_mxid(),
                "csrf_token": csrf_token,
            },
            status_code=400,
        )
        if set_cookie:
            resp.set_cookie(
                admin.CSRF_COOKIE_NAME,
                csrf_token,
                httponly=True,
                secure=admin.COOKIE_SECURE,
                samesite="lax",
            )
        return resp

    r = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r.scalar_one_or_none()
    if not bot_user:
        raise HTTPException(404, "BotUser не найден")
    notify_selected = [str(x).strip() for x in (bot_user.notify or ["all"]) if str(x).strip()]
    status_keys = {item["key"] for item in statuses_catalog}
    status_default_keys = [item["key"] for item in statuses_catalog if item.get("is_default")]
    preset = admin._status_preset(bot_user.notify, status_default_keys)
    if preset == "default":
        status_selected = status_default_keys
    else:
        status_selected = [k for k in notify_selected if k in status_keys]

    resp = admin.templates.TemplateResponse(
        request,
        "panel/my_settings.html",
        {
            "room": bot_user.room,
            "status_json": json.dumps(bot_user.notify, ensure_ascii=False)
            if bot_user.notify is not None
            else '["all"]',
            "status_preset": preset,
            "status_selected": status_selected,
            "statuses_catalog": statuses_catalog,
            "work_hours": bot_user.work_hours or "",
            "work_hours_from": admin._parse_work_hours_range(bot_user.work_hours or "")[0],
            "work_hours_to": admin._parse_work_hours_range(bot_user.work_hours or "")[1],
            "timezone_name": bot_user.timezone or os.getenv("BOT_TIMEZONE", "Europe/Moscow"),
            "timezone_top_options": admin._top_timezone_options(),
            "timezone_all_options": admin._standard_timezone_options(),
            "timezone_labels": admin._timezone_labels(admin._standard_timezone_options()),
            "work_days_json": json.dumps(bot_user.work_days, ensure_ascii=False)
            if bot_user.work_days is not None
            else "",
            "work_days_selected": bot_user.work_days
            if bot_user.work_days is not None
            else [0, 1, 2, 3, 4],
            "dnd": bool(bot_user.dnd),
            "error": None,
            "matrix_bot_mxid": admin._matrix_bot_mxid(),
            "csrf_token": csrf_token,
        },
    )
    if set_cookie:
        resp.set_cookie(
            admin.CSRF_COOKIE_NAME,
            csrf_token,
            httponly=True,
            secure=admin.COOKIE_SECURE,
            samesite="lax",
        )
    return resp


@router.post("/me/settings")
async def me_settings_post(
    request: Request,
    status_json: Annotated[str, Form()] = "",
    status_preset: Annotated[str, Form()] = "all",
    status_values: Annotated[list[str], Form()] = [],
    timezone_name: Annotated[str, Form()] = "",
    work_hours: Annotated[str, Form()] = "",
    work_hours_from: Annotated[str, Form()] = "",
    work_hours_to: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    work_days_values: Annotated[list[str], Form()] = [],
    dnd: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    statuses_catalog = await admin._load_statuses_catalog(session)
    status_allowed = [item["key"] for item in statuses_catalog]
    admin._verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if getattr(user, "role", "") == "admin":
        return RedirectResponse(admin.DASHBOARD_PATH, status_code=303)

    redmine_id = getattr(user, "redmine_id", None)
    if redmine_id is None:
        raise HTTPException(
            400,
            "Нет привязки к Redmine: настройте подписку через бота в Matrix или обратитесь к администратору.",
        )

    r = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r.scalar_one_or_none()
    if not bot_user:
        raise HTTPException(404, "BotUser не найден")

    if status_preset == "default":
        bot_user.notify = ["all"]
    elif status_preset == "new_only":
        bot_user.notify = ["new"]
    elif status_preset == "overdue_only":
        bot_user.notify = ["overdue"]
    elif status_preset == "custom":
        bot_user.notify = admin._normalize_notify(status_values, status_allowed)
    else:
        bot_user.notify = admin._parse_notify(status_json)
    bot_user.timezone = (timezone_name or "").strip() or None
    if work_hours_from and work_hours_to:
        bot_user.work_hours = f"{work_hours_from.strip()}-{work_hours_to.strip()}"
    else:
        bot_user.work_hours = work_hours.strip() or None
    if work_days_values:
        bot_user.work_days = sorted({int(v) for v in work_days_values if str(v).isdigit()})
    else:
        bot_user.work_days = admin._parse_work_days(work_days_json)
    bot_user.dnd = dnd in ("on", "true", "1")
    await session.flush()

    await admin._maybe_log_admin_crud(
        session,
        user,
        "self_settings",
        "update",
        {"bot_user_id": bot_user.id, "redmine_id": redmine_id},
    )
    return RedirectResponse("/me/settings", status_code=303)
