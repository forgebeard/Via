"""API шаблонов уведомлений v2 (Jinja2 + таблица ``notification_templates``)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.ext.asyncio import AsyncSession

from bot.template_loader import read_default_file
from database.notification_template_repo import (
    TEMPLATE_NAMES,
    clear_override,
    get_template_row,
    list_all_templates,
    upsert_template_body,
)
from database.session import get_session

router = APIRouter(tags=["notification-templates"])


def _admin() -> object:
    import admin.main as _m

    return _m


def _mock_context_for_preview(name: str) -> dict[str, Any]:
    base = {
        "issue_id": 101,
        "issue_url": "https://redmine.example/issues/101",
        "subject": "Пример темы",
        "status": "В работе",
        "priority": "Нормальный",
        "version": "РЕД ОС 8",
        "emoji": "📝",
        "title": "Предпросмотр",
        "event_type": "comment",
        "extra_text": "Тестовое описание журнала",
        "reminder_text": "Нет активности 4 ч",
        "items": [
            {"issue_id": 1, "subject": "Задача A", "event_type": "comment"},
            {"issue_id": 2, "subject": "Задача B", "event_type": "status_change"},
        ],
    }
    if name == "tpl_digest":
        return {"items": base["items"]}
    if name == "tpl_dry_run":
        return {k: base[k] for k in ("issue_id", "issue_url", "subject")}
    return base


@router.get("/api/bot/notification-templates", response_class=JSONResponse)
async def notification_templates_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    rows = {r.name: r for r in await list_all_templates(session)}
    out: list[dict[str, Any]] = []
    for name in TEMPLATE_NAMES:
        row = rows.get(name)
        default_html = read_default_file(name) or ""
        out.append(
            {
                "name": name,
                "default_html": default_html,
                "override_html": (row.body_html if row else None),
                "override_plain": (row.body_plain if row else None),
                "updated_at": (row.updated_at.isoformat() if row and row.updated_at else None),
            }
        )
    return {"ok": True, "templates": out}


@router.put("/api/bot/notification-templates/{name}", response_class=JSONResponse)
async def notification_templates_put(
    request: Request,
    name: str,
    body_html: Annotated[str, Form()] = "",
    body_plain: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    admin._verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    if name not in TEMPLATE_NAMES:
        raise HTTPException(400, "Неизвестное имя шаблона")

    ctx = _mock_context_for_preview(name)
    src = (body_html or "").strip()
    if src:
        env = SandboxedEnvironment(autoescape=True)
        try:
            env.from_string(src).render(**ctx)
        except Exception as e:
            raise HTTPException(400, f"Ошибка шаблона: {e}") from e

    await upsert_template_body(
        session,
        name=name,
        body_html=body_html.strip() or None,
        body_plain=(body_plain.strip() or None) if body_plain else None,
        updated_by=getattr(user, "login", None) or getattr(user, "email", None),
    )
    await session.commit()
    return {"ok": True}


@router.post("/api/bot/notification-templates/{name}/reset", response_class=JSONResponse)
async def notification_templates_reset(
    request: Request,
    name: str,
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    admin._verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    if name not in TEMPLATE_NAMES:
        raise HTTPException(400, "Неизвестное имя шаблона")
    await clear_override(session, name)
    await session.commit()
    return {"ok": True}


@router.post("/api/bot/notification-templates/preview", response_class=JSONResponse)
async def notification_templates_preview(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Некорректный JSON") from exc
    name = str(payload.get("name") or "").strip()
    if name not in TEMPLATE_NAMES:
        raise HTTPException(400, "Неизвестное имя шаблона")
    html_src = str(payload.get("body_html") or "").strip()
    ctx = payload.get("context")
    if not isinstance(ctx, dict):
        ctx = _mock_context_for_preview(name)
    env = SandboxedEnvironment(autoescape=True)
    try:
        if html_src:
            html = env.from_string(html_src).render(**ctx)
        else:
            default = read_default_file(name) or ""
            html = env.from_string(default).render(**ctx)
    except Exception as e:
        raise HTTPException(400, f"Ошибка рендера: {e}") from e
    return {"ok": True, "html": html}
