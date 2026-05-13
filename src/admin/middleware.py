"""Middleware для админки: аутентификация и security headers."""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from admin.helpers import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SETUP_PATH,
    _ensure_csrf,
    _has_admin,
    _now_utc,  # re-export for db_config.py
)
from admin.helpers_ext import _integration_status
from database.models import BotAppUser, BotSession
from database.session import get_session_factory

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("redmine_admin")


# ── CSP / Security headers middleware ────────────────────────────────────────


def _admin_csp_value() -> str | None:
    """Content-Security-Policy для HTML-ответов."""
    explicit = (os.getenv("ADMIN_CSP_POLICY") or "").strip()
    if explicit:
        return explicit
    if os.getenv("ADMIN_ENABLE_CSP", "").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    return (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "connect-src 'self';"
    )


class CspSecurityMiddleware:
    """Добавляет CSP, X-Content-Type-Options, X-Frame-Options ко всем ответам."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                csp = _admin_csp_value()
                if csp:
                    headers.append((b"content-security-policy", csp.encode()))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ── Auth middleware ──────────────────────────────────────────────────────────

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0").strip().lower() in ("1", "true", "yes", "on")
SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("ADMIN_SESSION_IDLE_TIMEOUT", "1800"))
_ADMIN_HTTP_TRACE = (os.getenv("ADMIN_HTTP_TRACE") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _machine_api_path_allowed(path: str, method: str) -> bool:
    p = (path or "").strip()
    m = (method or "").upper()
    if p == "/api/bot/commands" and m == "GET":
        return True
    if p.startswith("/api/bot/commands/") and m == "POST":
        tail = p.removeprefix("/api/bot/commands/")
        return tail.endswith("/ack") or tail.endswith("/error")
    return False


def _expected_bot_api_token() -> str:
    return (os.getenv("BOT_INTERNAL_API_TOKEN") or "").strip()


def _machine_auth_ok(request: Request) -> bool:
    expected = _expected_bot_api_token()
    if not expected:
        return False
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return False
    provided = auth[7:].strip()
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


class AuthMiddleware(BaseHTTPMiddleware):
    """Аутентификация через session cookie, CSRF."""

    async def dispatch(self, request: Request, call_next):
        if _ADMIN_HTTP_TRACE:
            logger.debug("[MW] >>> %s %s", request.method, request.url.path)
        p = request.url.path
        method = request.method

        if _machine_api_path_allowed(p, method):
            if _machine_auth_ok(request):
                return await call_next(request)
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

        # ── Пропускаем без проверки ──
        if (
            p.startswith("/static/")
            or p == "/favicon.ico"
            or p in ("/health", "/health/live", "/health/ready")
            or p.startswith("/docs")
            or p in ("/openapi.json", "/redoc")
        ):
            return await call_next(request)

        # ── Публичные auth-страницы ──
        if p in ("/login", "/forgot-password", "/reset-password", SETUP_PATH) or p.startswith(
            "/reset-password"
        ):
            return await call_next(request)

        # ── Проверяем наличие админа ──
        try:
            factory = get_session_factory()
            async with factory() as session:
                has_admin = await _has_admin(session)
        except Exception:
            from fastapi.responses import RedirectResponse

            return RedirectResponse("/login", status_code=303)

        if not has_admin and p != SETUP_PATH:
            from fastapi.responses import RedirectResponse

            return RedirectResponse(SETUP_PATH, status_code=303)

        # ── Проверяем session cookie ──
        token_raw = request.cookies.get(SESSION_COOKIE_NAME, "")
        if not token_raw:
            from fastapi.responses import RedirectResponse

            return RedirectResponse("/login", status_code=303)

        try:
            token_uuid = uuid.UUID(token_raw)
        except Exception:
            from fastapi.responses import RedirectResponse

            resp = RedirectResponse("/login", status_code=303)
            resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
            return resp

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
                    from fastapi.responses import RedirectResponse

                    return RedirectResponse("/login", status_code=303)

                u = await session.execute(select(BotAppUser).where(BotAppUser.id == sess.user_id))
                user = u.scalar_one_or_none()
                if not user:
                    from fastapi.responses import RedirectResponse

                    return RedirectResponse("/login", status_code=303)
                if sess.session_version != getattr(user, "session_version", 1):
                    from fastapi.responses import RedirectResponse

                    return RedirectResponse("/login", status_code=303)

                # Sliding idle timeout
                sess.expires_at = now + timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
                await session.flush()
                await session.commit()

                request.state.current_user = user
                request.state.integration_status = await _integration_status(session)
        except Exception:
            from fastapi.responses import RedirectResponse

            return RedirectResponse("/login", status_code=303)

        # CSRF
        csrf_token, set_csrf_cookie = _ensure_csrf(request)
        request.state.csrf_token = csrf_token

        response = await call_next(request)
        if _ADMIN_HTTP_TRACE:
            logger.debug("[MW] <<< %s %s -> %s", method, p, response.status_code)
        if set_csrf_cookie:
            response.set_cookie(
                CSRF_COOKIE_NAME,
                csrf_token,
                httponly=True,
                secure=COOKIE_SECURE,
                samesite="lax",
                path="/",
            )
        return response
