"""
Веб-админка: пользователи бота и маршруты Matrix (Postgres).

Запуск: uvicorn admin_main:app --host 0.0.0.0 --port 8080
Требуется DATABASE_URL, ADMIN_TOKEN (доступ к UI).
"""

from __future__ import annotations

import asyncio
import json
from html import escape as html_escape
import os
import sys
from pathlib import Path
from typing import Annotated
from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.load_config import row_counts
from database.models import BotUser, StatusRoomRoute, VersionRoomRoute
from database.session import get_session

from redminelib import Redmine
from redminelib.exceptions import BaseRedmineError

_templates_dir = str(_ROOT / "templates" / "admin")
# В некоторых наборах версий Jinja2/Starlette кэш шаблонов может приводить к TypeError
# (unhashable type: 'dict'). Отключаем кэш, чтобы /login работал стабильно.
_jinja_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=True,
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)

app = FastAPI(title="Redmine→Matrix admin", version="0.1.0")


def _admin_token() -> str:
    return (os.getenv("ADMIN_TOKEN") or "").strip()


REDMINE_URL = (os.getenv("REDMINE_URL") or "").strip()
REDMINE_API_KEY = (os.getenv("REDMINE_API_KEY") or "").strip()


def _redmine_client() -> Redmine | None:
    if not REDMINE_URL or not REDMINE_API_KEY:
        return None
    return Redmine(REDMINE_URL, key=REDMINE_API_KEY)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Cookie / X-Admin-Token; без токена — только /login и /health."""

    async def dispatch(self, request: Request, call_next):
        p = request.url.path
        if p in ("/login", "/health") or p.startswith("/docs") or p in ("/openapi.json", "/redoc"):
            return await call_next(request)
        expected = _admin_token()
        if not expected:
            return HTMLResponse(
                "<p>Задайте ADMIN_TOKEN в окружении.</p>",
                status_code=503,
                media_type="text/html; charset=utf-8",
            )
        c = request.cookies.get("admin_token", "")
        h = request.headers.get("X-Admin-Token", "")
        if c == expected or h == expected:
            return await call_next(request)
        return RedirectResponse("/login", status_code=303)


app.add_middleware(AdminAuthMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None},
    )


@app.post("/login")
async def login_post(request: Request, token: Annotated[str, Form()]):
    expected = _admin_token()
    if not expected:
        raise HTTPException(503, "ADMIN_TOKEN не задан")
    if token.strip() != expected:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный токен"},
            status_code=401,
        )
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        "admin_token",
        token.strip(),
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return resp


@app.get("/logout")
async def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie("admin_token")
    return r


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    nu, ns, nv = await row_counts(session)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "users_count": nu,
            "status_routes_count": ns,
            "version_routes_count": nv,
        },
    )


# --- Пользователи ---


@app.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(select(BotUser).order_by(BotUser.redmine_id))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "users_list.html",
        {"users": rows},
    )


@app.get("/users/new", response_class=HTMLResponse)
async def users_new(request: Request):
    return templates.TemplateResponse(
        request,
        "user_form.html",
        {
            "title": "Новый пользователь",
            "u": None,
            "notify_json": '["all"]',
        },
    )


def _parse_notify(raw: str) -> list:
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else ["all"]
    except json.JSONDecodeError:
        return ["all"]


def _parse_work_days(raw: str) -> list[int] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else None
    except json.JSONDecodeError:
        return None


@app.post("/users")
async def users_create(
    redmine_id: Annotated[int, Form()],
    room: Annotated[str, Form()],
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    wh = work_hours.strip() or None
    wd = _parse_work_days(work_days_json)
    row = BotUser(
        redmine_id=redmine_id,
        room=room.strip(),
        notify=_parse_notify(notify_json),
        work_hours=wh,
        work_days=wd,
        dnd=dnd in ("on", "true", "1"),
    )
    session.add(row)
    await session.flush()
    return RedirectResponse("/users", status_code=303)


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def users_edit(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(BotUser, user_id)
    if not row:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "user_form.html",
        {
            "title": f"Пользователь Redmine {row.redmine_id}",
            "u": row,
            "notify_json": json.dumps(row.notify, ensure_ascii=False),
        },
    )


@app.post("/users/{user_id}")
async def users_update(
    user_id: int,
    redmine_id: Annotated[int, Form()],
    room: Annotated[str, Form()],
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(BotUser, user_id)
    if not row:
        raise HTTPException(404)
    row.redmine_id = redmine_id
    row.room = room.strip()
    row.notify = _parse_notify(notify_json)
    row.work_hours = work_hours.strip() or None
    row.work_days = _parse_work_days(work_days_json)
    row.dnd = dnd in ("on", "true", "1")
    return RedirectResponse("/users", status_code=303)


@app.post("/users/{user_id}/delete")
async def users_delete(
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(BotUser, user_id)
    if row:
        await session.delete(row)
    return RedirectResponse("/users", status_code=303)


# --- Redmine: поиск users по имени/логину ---


@app.get("/redmine/users/search", response_class=HTMLResponse)
async def redmine_users_search(q: str = "", limit: int = 20):
    """
    Возвращает HTML-параметры <option> для автозаполнения редмине_id.

    Важно: endpoint может быть использован даже без доступной Redmine-конфигурации —
    тогда просто вернёт пустой ответ.
    """
    q = (q or "").strip()
    try:
        limit_i = int(limit)
    except ValueError:
        limit_i = 20
    limit_i = max(1, min(limit_i, 50))

    if not q or not _redmine_client():
        return HTMLResponse("")

    redmine = _redmine_client()

    def _do_search() -> list[dict]:
        # python-redmine: redmine.user.filter(...params...) прокидывает фильтры в REST
        # (для Redmine ожидается параметр `name` для поиска по логину/имени).
        users = []
        try:
            res = redmine.user.filter(name=q, limit=limit_i)
            users = list(res)
        except BaseRedmineError:
            users = []
        except Exception:
            users = []
        return users

    users = await asyncio.to_thread(_do_search)

    opts: list[str] = []
    for u in users:
        uid = getattr(u, "id", None)
        if uid is None:
            continue
        firstname = getattr(u, "firstname", "") or ""
        lastname = getattr(u, "lastname", "") or ""
        login = getattr(u, "login", "") or ""
        label = " ".join([s for s in (firstname, lastname) if s]).strip()
        if not label:
            label = login or str(uid)
        # value должен быть числом redmine_id
        opts.append(
            f'<option value="{int(uid)}">{html_escape(label)}'
            f'{(" (" + html_escape(login) + ")") if login else ""}</option>'
        )
    return HTMLResponse("".join(opts))


# --- Маршруты по статусу ---


@app.get("/routes/status", response_class=HTMLResponse)
async def routes_status(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(select(StatusRoomRoute).order_by(StatusRoomRoute.status_key))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "routes_status.html",
        {"rows": rows},
    )


@app.post("/routes/status")
async def routes_status_add(
    status_key: Annotated[str, Form()],
    room_id: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    session.add(StatusRoomRoute(status_key=status_key.strip(), room_id=room_id.strip()))
    return RedirectResponse("/routes/status", status_code=303)


@app.post("/routes/status/{row_id}/delete")
async def routes_status_del(
    row_id: int,
    session: AsyncSession = Depends(get_session),
):
    await session.execute(delete(StatusRoomRoute).where(StatusRoomRoute.id == row_id))
    return RedirectResponse("/routes/status", status_code=303)


# --- Маршруты по версии ---


@app.get("/routes/version", response_class=HTMLResponse)
async def routes_version(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(select(VersionRoomRoute).order_by(VersionRoomRoute.version_key))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "routes_version.html",
        {"rows": rows},
    )


@app.post("/routes/version")
async def routes_version_add(
    version_key: Annotated[str, Form()],
    room_id: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    session.add(VersionRoomRoute(version_key=version_key.strip(), room_id=room_id.strip()))
    return RedirectResponse("/routes/version", status_code=303)


@app.post("/routes/version/{row_id}/delete")
async def routes_version_del(
    row_id: int,
    session: AsyncSession = Depends(get_session),
):
    await session.execute(delete(VersionRoomRoute).where(VersionRoomRoute.id == row_id))
    return RedirectResponse("/routes/version", status_code=303)
