"""
Веб-админка: пользователи бота и маршруты Matrix (Postgres).

Запуск: uvicorn admin_main:app --host 0.0.0.0 --port 8080
Требуется DATABASE_URL (доступ к UI — через email magic-link).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from html import escape as html_escape
import os
import sys
import secrets
import uuid
from pathlib import Path
from typing import Annotated
from datetime import datetime, timedelta, timezone
from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nio import AsyncClient

from database.load_config import row_counts
from database.models import (
    BotMagicToken,
    BotSession,
    BotAppUser,
    BotUser,
    MatrixRoomBinding,
    StatusRoomRoute,
    VersionRoomRoute,
)
from database.session import get_session, get_session_factory

from redminelib import Redmine
from redminelib.exceptions import BaseRedmineError

from matrix_send import room_send_with_retry

_templates_dir = str(_ROOT / "templates" / "admin")
# В некоторых наборах версий Jinja2/Starlette кэш шаблонов может приводить к TypeError
# (unhashable type: 'dict'). Отключаем кэш, чтобы /login работал стабильно.
_jinja_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=True,
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)

app = FastAPI(title="Matrix bot control panel", version="0.1.0")

SESSION_COOKIE_NAME = os.getenv("ADMIN_SESSION_COOKIE", "admin_session")

AUTH_TOKEN_SALT = os.getenv("AUTH_TOKEN_SALT", "dev-token-salt")
MAGIC_TOKEN_TTL_SECONDS = int(os.getenv("MAGIC_TOKEN_TTL_SECONDS", "900"))
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))

_ADMIN_EMAILS = {
    e.strip().lower()
    for e in (os.getenv("ADMIN_EMAILS", "") or "").split(",")
    if e.strip()
}

ADMIN_BOOTSTRAP_FIRST_ADMIN = (os.getenv("ADMIN_BOOTSTRAP_FIRST_ADMIN", "0").strip().lower() in ("1", "true", "yes", "on"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(value: str) -> str:
    return hashlib.sha256((value + AUTH_TOKEN_SALT).encode("utf-8")).hexdigest()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Auth для админки через DB-сессии, которые выдаются после email magic-link.
    """

    async def dispatch(self, request: Request, call_next):
        p = request.url.path
        if p in ("/login", "/magic", "/health") or p.startswith("/docs") or p in (
            "/openapi.json",
            "/redoc",
        ):
            return await call_next(request)

        token_raw = request.cookies.get(SESSION_COOKIE_NAME, "")
        if not token_raw:
            return RedirectResponse("/login", status_code=303)

        try:
            token_uuid = uuid.UUID(token_raw)
        except Exception:
            return RedirectResponse("/login", status_code=303)

        factory = get_session_factory()
        try:
            async with factory() as session:
                now = _now_utc()
                s = await session.execute(
                    select(BotSession).where(
                        BotSession.session_token == token_uuid,
                        BotSession.expires_at > now,
                    )
                )
                sess = s.scalar_one_or_none()
                if not sess:
                    return RedirectResponse("/login", status_code=303)

                u = await session.execute(
                    select(BotAppUser).where(BotAppUser.id == sess.user_id)
                )
                user = u.scalar_one_or_none()
                if not user:
                    return RedirectResponse("/login", status_code=303)

                request.state.current_user = user
        except Exception:
            return RedirectResponse("/login", status_code=303)

        return await call_next(request)


REDMINE_URL = (os.getenv("REDMINE_URL") or "").strip()
REDMINE_API_KEY = (os.getenv("REDMINE_API_KEY") or "").strip()


def _redmine_client() -> Redmine | None:
    if not REDMINE_URL or not REDMINE_API_KEY:
        return None
    return Redmine(REDMINE_URL, key=REDMINE_API_KEY)


app.add_middleware(AuthMiddleware)


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
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Введите email"},
            status_code=400,
        )

    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    expires_at = _now_utc() + timedelta(seconds=MAGIC_TOKEN_TTL_SECONDS)

    # Magic token одноразовый (used_at будет выставлен в /magic).
    mt = BotMagicToken(
        id=uuid.uuid4(),
        email=email,
        token_hash=token_hash,
        expires_at=expires_at,
        used_at=None,
    )
    session.add(mt)
    await session.flush()

    # SMTP в MVP не форсируем: если нет SMTP-конфига — сразу редиректим на /magic.
    resp = RedirectResponse(f"/magic?token={token}", status_code=303)
    return resp


@app.get("/magic")
async def magic_get(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
):
    token = (token or "").strip()
    if not token:
        return RedirectResponse("/login", status_code=303)

    token_hash = _token_hash(token)
    now = _now_utc()

    r = await session.execute(
        select(BotMagicToken).where(
            BotMagicToken.token_hash == token_hash,
            BotMagicToken.used_at.is_(None),
            BotMagicToken.expires_at > now,
        )
    )
    mt = r.scalar_one_or_none()
    if not mt:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Magic-link истёк или недействителен"},
            status_code=401,
        )

    mt.used_at = now

    # Создаём app-user (1-й verified станет admin).
    rr = await session.execute(select(BotAppUser).where(BotAppUser.email == mt.email))
    existing_user = rr.scalar_one_or_none()

    if existing_user is None:
        # Проверяем: есть ли уже хотя бы один verified user.
        any_verified_q = await session.execute(
            select(BotAppUser).where(BotAppUser.verified_at.is_not(None)).limit(1)
        )
        has_any = any_verified_q.scalar_one_or_none() is not None
        # Если задан allow-list ADMIN_EMAILS — роль admin выдаём только по ней.
        # Если allow-list не задана:
        #   - ADMIN_BOOTSTRAP_FIRST_ADMIN=1 разрешает dev/bootstrap: первый verified → admin
        #   - иначе все создаются как user (чтобы "левый email" не получил доступ)
        if _ADMIN_EMAILS:
            role = "admin" if mt.email.lower() in _ADMIN_EMAILS else "user"
        else:
            if ADMIN_BOOTSTRAP_FIRST_ADMIN and not has_any:
                role = "admin"
            else:
                role = "user"

        user = BotAppUser(
            id=uuid.uuid4(),
            email=mt.email,
            role=role,
            verified_at=now,
            redmine_id=None,
        )
        session.add(user)
        await session.flush()
    else:
        user = existing_user
        user.verified_at = user.verified_at or now

    st = BotSession(
        session_token=uuid.uuid4(),
        user_id=user.id,
        expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
    )
    session.add(st)
    await session.flush()

    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        str(st.session_token),
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return resp


@app.get("/logout")
async def logout(request: Request, session: AsyncSession = Depends(get_session)):
    token_raw = request.cookies.get(SESSION_COOKIE_NAME, "")
    if token_raw:
        try:
            token_uuid = uuid.UUID(token_raw)
            await session.execute(
                delete(BotSession).where(BotSession.session_token == token_uuid)
            )
        except Exception:
            pass

    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
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
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    r = await session.execute(select(BotUser).order_by(BotUser.redmine_id))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "users_list.html",
        {"users": rows},
    )


@app.get("/users/new", response_class=HTMLResponse)
async def users_new(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
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
    request: Request,
    redmine_id: Annotated[int, Form()],
    room: Annotated[str, Form()],
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
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
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
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
    request: Request,
    user_id: int,
    redmine_id: Annotated[int, Form()],
    room: Annotated[str, Form()],
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
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
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    row = await session.get(BotUser, user_id)
    if row:
        await session.delete(row)
    return RedirectResponse("/users", status_code=303)


# --- Redmine: поиск users по имени/логину ---


@app.get("/redmine/users/search", response_class=HTMLResponse)
async def redmine_users_search(
    request: Request,
    q: str = "",
    limit: int = 20,
):
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

    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

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
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    r = await session.execute(select(StatusRoomRoute).order_by(StatusRoomRoute.status_key))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "routes_status.html",
        {"rows": rows},
    )


@app.post("/routes/status")
async def routes_status_add(
    request: Request,
    status_key: Annotated[str, Form()],
    room_id: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    session.add(StatusRoomRoute(status_key=status_key.strip(), room_id=room_id.strip()))
    return RedirectResponse("/routes/status", status_code=303)


@app.post("/routes/status/{row_id}/delete")
async def routes_status_del(
    request: Request,
    row_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    await session.execute(delete(StatusRoomRoute).where(StatusRoomRoute.id == row_id))
    return RedirectResponse("/routes/status", status_code=303)


# --- Маршруты по версии ---


@app.get("/routes/version", response_class=HTMLResponse)
async def routes_version(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    r = await session.execute(select(VersionRoomRoute).order_by(VersionRoomRoute.version_key))
    rows = list(r.scalars().all())
    return templates.TemplateResponse(
        request,
        "routes_version.html",
        {"rows": rows},
    )


@app.post("/routes/version")
async def routes_version_add(
    request: Request,
    version_key: Annotated[str, Form()],
    room_id: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    session.add(VersionRoomRoute(version_key=version_key.strip(), room_id=room_id.strip()))
    return RedirectResponse("/routes/version", status_code=303)


@app.post("/routes/version/{row_id}/delete")
async def routes_version_del(
    request: Request,
    row_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    await session.execute(delete(VersionRoomRoute).where(VersionRoomRoute.id == row_id))
    return RedirectResponse("/routes/version", status_code=303)


# --- Matrix room binding (one-time code) ---


@app.get("/matrix/bind", response_class=HTMLResponse)
async def matrix_bind_page(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    redmine_id = getattr(user, "redmine_id", None) or ""
    return HTMLResponse(
        f"""
<html><head><meta charset="utf-8"/></head><body>
<h2>Связать Matrix комнату</h2>
<p>1) Укажите Redmine id и room_id, нажмите «Отправить код».</p>
<form method="post" action="/matrix/bind/start">
  <label>Redmine id <input name="redmine_id" value="{redmine_id}" required/></label><br/>
  <label>room_id <input name="room_id" value="" required/></label><br/>
  <button type="submit">Отправить код</button>
</form>
<p>2) Вставьте полученный код и подтвердите:</p>
<form method="post" action="/matrix/bind/confirm">
  <input type="hidden" name="redmine_id" value="{redmine_id}"/>
  <label>room_id <input name="room_id" value="" required/></label><br/>
  <label>Код <input name="code" value="" required/></label><br/>
  <button type="submit">Подтвердить</button>
</form>
</body></html>
"""
    )


@app.post("/matrix/bind/start")
async def matrix_bind_start(
    request: Request,
    redmine_id: Annotated[int, Form()],
    room_id: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    room_id = room_id.strip()
    if not room_id:
        raise HTTPException(400, "room_id пуст")

    # Пользователь может связать комнату только для своей redmine_id.
    # Если redmine_id ещё не задан — позволяем впервые.
    if getattr(user, "redmine_id", None) is not None and getattr(user, "redmine_id", None) != redmine_id:
        raise HTTPException(403, "Можно привязать комнату только для своей Redmine-учётки")

    # 6-значный цифровой код.
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    code_hash = _token_hash(code)
    expires_at = _now_utc() + timedelta(seconds=MATRIX_CODE_TTL_SECONDS)

    row = MatrixRoomBinding(
        id=uuid.uuid4(),
        user_id=user.id,
        redmine_id=redmine_id,
        room_id=room_id,
        verify_code_hash=code_hash,
        expires_at=expires_at,
        used_at=None,
    )
    session.add(row)
    await session.flush()

    # Отправляем код в Matrix (если есть конфигурация).
    try:
        HOMESERVER = (os.getenv("MATRIX_HOMESERVER") or "").strip()
        ACCESS_TOKEN = (os.getenv("MATRIX_ACCESS_TOKEN") or "").strip()
        MATRIX_USER_ID = (os.getenv("MATRIX_USER_ID") or "").strip()
        MATRIX_DEVICE_ID = (os.getenv("MATRIX_DEVICE_ID") or "").strip()
        if HOMESERVER and ACCESS_TOKEN and MATRIX_USER_ID:
            mclient = AsyncClient(HOMESERVER)
            mclient.access_token = ACCESS_TOKEN
            mclient.user_id = MATRIX_USER_ID
            mclient.device_id = MATRIX_DEVICE_ID
            await room_send_with_retry(
                mclient,
                room_id,
                {
                    "msgtype": "m.text",
                    "body": f"Код подтверждения: {code}",
                    "format": "org.matrix.custom.html",
                    "formatted_body": f"<b>Код подтверждения:</b> {code}",
                },
            )
            await mclient.close()
    except Exception:
        # В dev/CI может не быть Matrix-конфига — UI всё равно работает как верификация по коду.
        pass

    dev_echo = os.getenv("MATRIX_CODE_DEV_ECHO", "0").strip().lower() in ("1", "true", "yes", "on")
    dev_line = f"<p><b>Dev code:</b> {code}</p>" if dev_echo else ""

    return HTMLResponse(
        f"""
<html><head><meta charset="utf-8"/></head><body>
<h2>Код отправлен</h2>
{dev_line}
<p>Введите код на этой же странице ниже.</p>
<form method="post" action="/matrix/bind/confirm">
  <input type="hidden" name="redmine_id" value="{redmine_id}"/>
  <label>room_id <input name="room_id" value="{room_id}" required/></label><br/>
  <label>Код <input name="code" value="" required/></label><br/>
  <button type="submit">Подтвердить</button>
</form>
</body></html>
"""
    )


@app.post("/matrix/bind/confirm")
async def matrix_bind_confirm(
    request: Request,
    redmine_id: Annotated[int, Form()],
    room_id: Annotated[str, Form()],
    code: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    room_id = room_id.strip()
    code = (code or "").strip()
    if not room_id or not code:
        raise HTTPException(400, "room_id и code обязательны")

    if getattr(user, "redmine_id", None) is not None and getattr(user, "redmine_id", None) != redmine_id:
        raise HTTPException(403, "Can’t change redmine_id after it is set")

    code_hash = _token_hash(code)
    now = _now_utc()

    r = await session.execute(
        select(MatrixRoomBinding).where(
            MatrixRoomBinding.user_id == user.id,
            MatrixRoomBinding.redmine_id == redmine_id,
            MatrixRoomBinding.room_id == room_id,
            MatrixRoomBinding.used_at.is_(None),
            MatrixRoomBinding.expires_at > now,
            MatrixRoomBinding.verify_code_hash == code_hash,
        )
    )
    binding = r.scalars().first()
    if not binding:
        return HTMLResponse("<p>Неверный код или срок истёк.</p>", status_code=401)

    binding.used_at = now

    # Обновляем привязку в app-user (redmine_id можно поставить только 1 раз).
    app_user = await session.get(BotAppUser, user.id)
    if app_user and app_user.redmine_id is None:
        app_user.redmine_id = redmine_id

    # Upsert bot_user (комната для отправки).
    r2 = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r2.scalar_one_or_none()
    if bot_user:
        bot_user.room = room_id
    else:
        session.add(BotUser(redmine_id=redmine_id, room=room_id))

    return RedirectResponse("/", status_code=303)


# --- User self-service: настройки ---


@app.get("/me/settings", response_class=HTMLResponse)
async def me_settings_get(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    redmine_id = getattr(user, "redmine_id", None)
    if redmine_id is None:
        return templates.TemplateResponse(
            request,
            "my_settings.html",
            {
                "room": None,
                "notify_json": '["all"]',
                "work_hours": "",
                "work_days_json": "",
                "dnd": False,
                "error": "Сначала привяжите комнату через Matrix binding.",
            },
            status_code=400,
        )

    r = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r.scalar_one_or_none()
    if not bot_user:
        raise HTTPException(404, "BotUser не найден")

    return templates.TemplateResponse(
        request,
        "my_settings.html",
        {
            "room": bot_user.room,
            "notify_json": json.dumps(bot_user.notify, ensure_ascii=False)
            if bot_user.notify is not None
            else '["all"]',
            "work_hours": bot_user.work_hours or "",
            "work_days_json": json.dumps(bot_user.work_days, ensure_ascii=False)
            if bot_user.work_days is not None
            else "",
            "dnd": bool(bot_user.dnd),
            "error": None,
        },
    )


@app.post("/me/settings")
async def me_settings_post(
    request: Request,
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    redmine_id = getattr(user, "redmine_id", None)
    if redmine_id is None:
        raise HTTPException(400, "Сначала привяжите комнату через Matrix binding.")

    r = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r.scalar_one_or_none()
    if not bot_user:
        raise HTTPException(404, "BotUser не найден")

    bot_user.notify = _parse_notify(notify_json)
    bot_user.work_hours = work_hours.strip() or None
    bot_user.work_days = _parse_work_days(work_days_json)
    bot_user.dnd = dnd in ("on", "true", "1")
    await session.flush()

    return RedirectResponse("/me/settings", status_code=303)
