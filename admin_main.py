"""
Веб-админка: пользователи бота и маршруты Matrix (Postgres).

Запуск: uvicorn admin_main:app --host 0.0.0.0 --port 8080
Требуется DATABASE_URL (доступ к UI — через email/password).
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
from collections import defaultdict, deque
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
    AppSecret,
    BotSession,
    BotAppUser,
    BotUser,
    PasswordResetToken,
    MatrixRoomBinding,
    StatusRoomRoute,
    VersionRoomRoute,
)
from database.session import get_session, get_session_factory
from security import (
    SecurityError,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    load_master_key,
    make_reset_token,
    token_hash,
    validate_password_policy,
    verify_password,
)

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
CSRF_COOKIE_NAME = os.getenv("ADMIN_CSRF_COOKIE", "admin_csrf")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0").strip().lower() in ("1", "true", "yes", "on")
SETUP_PATH = "/setup"

AUTH_TOKEN_SALT = os.getenv("AUTH_TOKEN_SALT", "dev-token-salt")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
RESET_TOKEN_TTL_SECONDS = int(os.getenv("RESET_TOKEN_TTL_SECONDS", "1800"))
RESET_COOLDOWN_SECONDS = int(os.getenv("RESET_COOLDOWN_SECONDS", "90"))

APP_MASTER_KEY_FILE = os.getenv("APP_MASTER_KEY_FILE", "/run/secrets/app_master_key")

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


def _generic_login_error() -> str:
    return "Неверный email или пароль"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _ensure_csrf(request: Request) -> tuple[str, bool]:
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        return token, False
    return secrets.token_urlsafe(24), True


def _verify_csrf(request: Request, form_token: str) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not cookie_token or not form_token or form_token != cookie_token:
        raise HTTPException(status_code=400, detail="Некорректный CSRF токен")


class _SimpleRateLimiter:
    """In-memory rate limiter (per process)."""

    def __init__(self):
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = datetime.now().timestamp()
        q = self._buckets[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


_rate_limiter = _SimpleRateLimiter()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Auth для админки через DB-сессии после login по email/password.
    """

    async def dispatch(self, request: Request, call_next):
        p = request.url.path
        if p in (
            "/login",
            "/forgot-password",
            "/reset-password",
            "/health",
            "/health/live",
            "/health/ready",
            SETUP_PATH,
        ) or p.startswith("/docs") or p in (
            "/openapi.json",
            "/redoc",
        ):
            return await call_next(request)

        try:
            factory = get_session_factory()
            async with factory() as session:
                any_admin = await session.execute(
                    select(BotAppUser.id).where(BotAppUser.role == "admin").limit(1)
                )
                has_admin = any_admin.scalar_one_or_none() is not None
        except Exception:
            # Если БД недоступна/не настроена, не падаем на middleware для публичных редиректов.
            return RedirectResponse("/login", status_code=303)

        if not has_admin and p != SETUP_PATH:
            return RedirectResponse(SETUP_PATH, status_code=303)

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
                if sess.session_version != getattr(user, "session_version", 1):
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


@app.on_event("startup")
async def startup_checks():
    # Fail-fast: без master key нельзя безопасно работать с encrypted secrets.
    try:
        load_master_key()
    except SecurityError as e:
        raise RuntimeError(f"startup failed: {e}") from e


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


@app.get("/health/ready")
async def health_ready(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(select(BotAppUser.id).limit(1))
        load_master_key()
    except SecurityError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=503, detail="service not ready")
    return {"status": "ready"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
        )
    return resp


@app.get(SETUP_PATH, response_class=HTMLResponse)
async def setup_page(request: Request, session: AsyncSession = Depends(get_session)):
    any_admin = await session.execute(select(BotAppUser.id).where(BotAppUser.role == "admin").limit(1))
    if any_admin.scalar_one_or_none() is not None:
        return RedirectResponse("/login", status_code=303)
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "setup.html",
        {"error": None, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
        )
    return resp


@app.post(SETUP_PATH)
async def setup_post(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Введите корректный email", "csrf_token": csrf_token},
            status_code=400,
        )
    ok, reason = validate_password_policy(password, email=email)
    if not ok:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": reason, "csrf_token": csrf_token},
            status_code=400,
        )
    # Protect from race: lock admin rows.
    await session.execute(select(BotAppUser.id).where(BotAppUser.role == "admin").with_for_update())
    any_admin = await session.execute(select(BotAppUser.id).where(BotAppUser.role == "admin").limit(1))
    if any_admin.scalar_one_or_none() is not None:
        return RedirectResponse("/login", status_code=303)
    user = BotAppUser(
        id=uuid.uuid4(),
        email=email,
        role="admin",
        verified_at=_now_utc(),
        password_hash=hash_password(password),
        session_version=1,
    )
    session.add(user)
    return RedirectResponse("/login", status_code=303)


@app.post("/login")
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    ip = _client_ip(request)
    if not _rate_limiter.hit(f"login:ip:{ip}", limit=5, window_seconds=60):
        raise HTTPException(429, "Слишком много попыток, попробуйте позже")

    email = (email or "").strip().lower()
    if not email or not password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": _generic_login_error(), "csrf_token": csrf_token},
            status_code=401,
        )
    r = await session.execute(select(BotAppUser).where(BotAppUser.email == email))
    user = r.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": _generic_login_error(), "csrf_token": csrf_token},
            status_code=401,
        )
    now = _now_utc()
    st = BotSession(
        session_token=uuid.uuid4(),
        user_id=user.id,
        expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
        session_version=user.session_version,
    )
    session.add(st)
    await session.flush()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        str(st.session_token),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return resp


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"error": None, "ok": None, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return resp


@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    email = (email or "").strip().lower()
    ip = _client_ip(request)
    if not _rate_limiter.hit(f"forgot:ip:{ip}", limit=5, window_seconds=60):
        raise HTTPException(429, "Слишком много попыток, попробуйте позже")
    if not _rate_limiter.hit(f"forgot:email:{email}", limit=3, window_seconds=3600):
        return templates.TemplateResponse(
            request,
            "forgot_password.html",
            {"error": "Слишком много запросов сброса, попробуйте позже", "ok": None, "csrf_token": csrf_token},
            status_code=429,
        )
    r = await session.execute(select(BotAppUser).where(BotAppUser.email == email))
    user = r.scalar_one_or_none()
    # Response must be generic.
    if user:
        token = make_reset_token()
        row = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash(token, AUTH_TOKEN_SALT),
            requested_email=email,
            expires_at=_now_utc() + timedelta(seconds=RESET_TOKEN_TTL_SECONDS),
            used_at=None,
        )
        session.add(row)
        await session.flush()
        # MVP/dev: show token directly in UI. Production should send email.
        return templates.TemplateResponse(
            request,
            "forgot_password.html",
            {
                "error": None,
                "ok": "Если email существует, ссылка на сброс отправлена.",
                "dev_token": token,
                "csrf_token": csrf_token,
            },
        )
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"error": None, "ok": "Если email существует, ссылка на сброс отправлена.", "csrf_token": csrf_token},
    )


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "reset_password.html",
        {"error": None, "token": token, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return resp


@app.post("/reset-password")
async def reset_password_post(
    request: Request,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    token = (token or "").strip()
    if not token or not password:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"error": "Неверный или просроченный токен", "token": token, "csrf_token": csrf_token},
            status_code=401,
        )
    now = _now_utc()
    r = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash(token, AUTH_TOKEN_SALT),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )
    rt = r.scalar_one_or_none()
    if not rt:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"error": "Неверный или просроченный токен", "token": token, "csrf_token": csrf_token},
            status_code=401,
        )
    u = await session.execute(select(BotAppUser).where(BotAppUser.id == rt.user_id))
    user = u.scalar_one_or_none()
    if not user:
        return RedirectResponse("/login", status_code=303)
    ok, reason = validate_password_policy(password, email=user.email)
    if not ok:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"error": reason, "token": token, "csrf_token": csrf_token},
            status_code=400,
        )
    user.password_hash = hash_password(password)
    user.session_version = (user.session_version or 1) + 1
    rt.used_at = now
    await session.execute(delete(BotSession).where(BotSession.user_id == user.id))
    return RedirectResponse("/login", status_code=303)


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
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
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


@app.get("/secrets", response_class=HTMLResponse)
async def secrets_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    rows = await session.execute(select(AppSecret).order_by(AppSecret.name))
    items = list(rows.scalars().all())
    csrf_token, set_cookie = _ensure_csrf(request)
    resp = templates.TemplateResponse(
        request,
        "secrets.html",
        {"items": items, "error": None, "csrf_token": csrf_token},
    )
    if set_cookie:
        resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return resp


@app.post("/secrets")
async def secrets_save(
    request: Request,
    name: Annotated[str, Form()],
    value: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    name = (name or "").strip()
    value = (value or "").strip()
    if not name or not value:
        raise HTTPException(400, "Имя и значение обязательны")
    key = load_master_key()
    enc = encrypt_secret(value, key=key)
    r = await session.execute(select(AppSecret).where(AppSecret.name == name))
    row = r.scalar_one_or_none()
    if row is None:
        row = AppSecret(name=name, ciphertext=enc.ciphertext, nonce=enc.nonce, key_version=enc.key_version)
        session.add(row)
    else:
        row.ciphertext = enc.ciphertext
        row.nonce = enc.nonce
        row.key_version = enc.key_version
    return RedirectResponse("/secrets", status_code=303)


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
    csrf_token, set_cookie = _ensure_csrf(request)
    if redmine_id is None:
        resp = templates.TemplateResponse(
            request,
            "my_settings.html",
            {
                "room": None,
                "notify_json": '["all"]',
                "work_hours": "",
                "work_days_json": "",
                "dnd": False,
                "error": "Сначала привяжите комнату через Matrix binding.",
                "csrf_token": csrf_token,
            },
            status_code=400,
        )
        if set_cookie:
            resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
        return resp

    r = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
    bot_user = r.scalar_one_or_none()
    if not bot_user:
        raise HTTPException(404, "BotUser не найден")

    resp = templates.TemplateResponse(
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
            "csrf_token": csrf_token,
        },
    )
    if set_cookie:
        resp.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return resp


@app.post("/me/settings")
async def me_settings_post(
    request: Request,
    notify_json: Annotated[str, Form()] = '["all"]',
    work_hours: Annotated[str, Form()] = "",
    work_days_json: Annotated[str, Form()] = "",
    dnd: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    _verify_csrf(request, csrf_token)
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
