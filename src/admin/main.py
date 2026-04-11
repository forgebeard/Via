"""
Веб-админка: пользователи бота и маршруты Matrix (Postgres).

Запуск: uvicorn admin_main:app --host 0.0.0.0 --port 8080
Требуется DATABASE_URL (доступ к UI — через логин и пароль).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo, available_timezones

if TYPE_CHECKING:
    from nio import AsyncClient

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from fastapi import Depends, FastAPI, Form, HTTPException, Request  # noqa: E402, I001
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from admin.crud_events_log import (  # noqa: E402
    actor_label_for_crud_log,
    format_crud_line,
    sanitize_audit_details,
    want_admin_audit_crud_db,
    want_admin_events_log_crud,
)

# Jinja2 окружение и шаблоны теперь в helpers.py — импортируем чтобы не было дубликатов
# и чтобы фильтры (dt_ui) работали во всех роутах.
from admin.helpers import _jinja_env  # noqa: E402
from database.models import (  # noqa: E402
    AppSecret,
    BotAppUser,
    BotOpsAudit,
    BotSession,
    BotUser,
    SupportGroup,
)
from database.session import get_session, get_session_factory  # noqa: E402
from events_log_display import (  # noqa: E402
    admin_events_log_timestamp_now,
)
from mail import mask_identifier  # noqa: E402
from ops.docker_control import control_service  # noqa: E402
from security import (  # noqa: E402
    SecurityError,
    decrypt_secret,
    encrypt_secret,
    load_master_key,
)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    logger.info("🚀 Admin panel starting up...")
    # Fail-fast: without master key we cannot safely work with encrypted secrets.
    try:
        load_master_key()
    except SecurityError as e:
        raise RuntimeError(f"startup failed: {e}") from e
    # Service timezone can be configured in onboarding and persisted as secret.
    try:
        factory = get_session_factory()
        async with factory() as session:
            tz_saved = await _load_secret_plain(session, SERVICE_TIMEZONE_SECRET)
        os.environ["BOT_TIMEZONE"] = _normalize_service_timezone_name(tz_saved)
    except Exception:
        logger.warning("service_timezone_load_failed", exc_info=True)
    logger.info("✅ Admin panel ready")
    yield
    logger.info("👋 Admin panel shutting down")


app = FastAPI(title="Matrix bot control panel", version="0.1.0", lifespan=_app_lifespan)

# Re-export для route-файлов (через _admin() late-import)
from admin.helpers import templates  # noqa: E402, F401
from ops.docker_control import get_service_status  # noqa: E402, F401

_STATIC_ROOT = _ROOT / "static"
if _STATIC_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_ROOT)), name="static")


def _admin_csp_value() -> str | None:
    """
    Content-Security-Policy для HTML-ответов.
    ADMIN_CSP_POLICY — полная строка политики (приоритет).
    ADMIN_ENABLE_CSP=1 — встроенная политика под текущие CDN (htmx, FA, Google Fonts)
    и inline script/style (обработчики в шаблонах до выноса в .js).
    """
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


@app.middleware("http")
async def _csp_middleware(request: Request, call_next):
    response = await call_next(request)
    csp = _admin_csp_value()
    if csp:
        response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


SESSION_COOKIE_NAME = os.getenv("ADMIN_SESSION_COOKIE", "admin_session")
CSRF_COOKIE_NAME = os.getenv("ADMIN_CSRF_COOKIE", "admin_csrf")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0").strip().lower() in ("1", "true", "yes", "on")
SETUP_PATH = "/setup"
# Путь дашборда в адресной строке (корень `/` отдаёт тот же экран без редиректа).
DASHBOARD_PATH = "/dashboard"
SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("ADMIN_SESSION_IDLE_TIMEOUT", "1800"))
RUNTIME_STATUS_FILE = os.getenv("BOT_RUNTIME_STATUS_FILE", "/app/data/runtime_status.json")
# Системная строка в support_groups (миграции); в UI не показываем как обычную группу.
GROUP_UNASSIGNED_NAME = "UNASSIGNED"
# Подпись в интерфейсе для пользователей без group_id и для фильтра «только без группы».
GROUP_UNASSIGNED_DISPLAY = "Без группы"
# Совпадает с подписью первой опции фильтра на /users — запись в support_groups с этим именем даёт дубль в select.
GROUP_USERS_FILTER_ALL_LABEL = "Все группы"

_jinja_env.globals["GROUP_UNASSIGNED_NAME"] = GROUP_UNASSIGNED_NAME
_jinja_env.globals["GROUP_UNASSIGNED_DISPLAY"] = GROUP_UNASSIGNED_DISPLAY
_jinja_env.globals["GROUP_USERS_FILTER_ALL_LABEL"] = GROUP_USERS_FILTER_ALL_LABEL
_jinja_env.globals["dashboard_path"] = DASHBOARD_PATH

AUTH_TOKEN_SALT = os.getenv("AUTH_TOKEN_SALT", "dev-token-salt")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
RESET_TOKEN_TTL_SECONDS = int(os.getenv("RESET_TOKEN_TTL_SECONDS", "1800"))
RESET_COOLDOWN_SECONDS = int(os.getenv("RESET_COOLDOWN_SECONDS", "90"))


@lru_cache(maxsize=1)
def _standard_timezone_options() -> list[str]:
    """IANA timezone list with RU priority zones first."""
    preferred = [
        "Europe/Moscow",
        "Asia/Ufa",
        "Asia/Yekaterinburg",
        "Asia/Omsk",
        "Asia/Krasnoyarsk",
        "Asia/Irkutsk",
        "Asia/Vladivostok",
    ]
    values = sorted(
        tz
        for tz in available_timezones()
        if "/" in tz and not tz.startswith(("Etc/", "posix/", "right/"))
    )
    ordered = [tz for tz in preferred if tz in values]
    preferred_set = set(ordered)
    ordered.extend([tz for tz in values if tz not in preferred_set])
    return ordered


@lru_cache(maxsize=1)
def _top_timezone_options() -> list[str]:
    """Frequently used timezones for the default compact select list."""
    preferred = [
        "Europe/Moscow",
        "Europe/Kaliningrad",
        "Europe/Samara",
        "Europe/Volgograd",
        "Europe/Astrakhan",
        "Europe/Ulyanovsk",
        "Europe/Kirov",
        "Europe/Simferopol",
        "Europe/Minsk",
        "Europe/Kyiv",
        "Europe/Riga",
        "Europe/Vilnius",
        "Europe/Tallinn",
        "Europe/Warsaw",
        "Europe/Berlin",
        "Europe/Paris",
        "Europe/London",
        "Europe/Madrid",
        "Europe/Rome",
        "Europe/Istanbul",
        "Asia/Yerevan",
        "Asia/Tbilisi",
        "Asia/Baku",
        "Asia/Almaty",
        "Asia/Tashkent",
        "Asia/Yekaterinburg",
        "Asia/Ufa",
        "Asia/Omsk",
        "Asia/Novosibirsk",
        "Asia/Krasnoyarsk",
        "Asia/Vladivostok",
    ]
    all_set = set(_standard_timezone_options())
    result = [tz for tz in preferred if tz in all_set]
    if len(result) < 30:
        for tz in _standard_timezone_options():
            if tz in result:
                continue
            result.append(tz)
            if len(result) >= 30:
                break
    return result[:30]


def _timezone_labels(options: list[str]) -> dict[str, str]:
    """Readable timezone labels with UTC offset and local time."""
    labels: dict[str, str] = {}
    for tz_name in options:
        try:
            now_local = datetime.now(ZoneInfo(tz_name))
            delta = now_local.utcoffset() or timedelta(0)
            total_minutes = int(delta.total_seconds() // 60)
            sign = "+" if total_minutes >= 0 else "-"
            abs_minutes = abs(total_minutes)
            hh = abs_minutes // 60
            mm = abs_minutes % 60
            labels[tz_name] = f"{tz_name} (UTC{sign}{hh:02d}:{mm:02d}, {now_local:%H:%M})"
        except Exception:
            labels[tz_name] = tz_name
    return labels


APP_MASTER_KEY_FILE = os.getenv("APP_MASTER_KEY_FILE", "/run/secrets/app_master_key")
SHOW_DEV_TOKENS = os.getenv("SHOW_DEV_TOKENS", "0").strip().lower() in ("1", "true", "yes", "on")
ADMIN_EXISTS_CACHE_TTL_SECONDS = int(os.getenv("ADMIN_EXISTS_CACHE_TTL_SECONDS", "20"))
INTEGRATION_STATUS_CACHE_TTL_SECONDS = int(os.getenv("INTEGRATION_STATUS_CACHE_TTL_SECONDS", "30"))
REQUIRED_SECRET_NAMES = [
    v.strip()
    for v in os.getenv(
        "REQUIRED_SECRET_NAMES",
        "REDMINE_URL,REDMINE_API_KEY,MATRIX_HOMESERVER,MATRIX_ACCESS_TOKEN,MATRIX_USER_ID",
    ).split(",")
    if v.strip()
]
MATRIX_DEFAULT_DEVICE_ID = (
    os.getenv("MATRIX_DEFAULT_DEVICE_ID") or "redmine_bot"
).strip() or "redmine_bot"


def _mask_secret(value: str, mask_url: bool = False) -> str:
    """Маскирует секретное значение.

    Для URL и MXID — показываем полностью (mask_url=False по умолчанию).
    Для ключей/токенов — показываем первые 6 и последние 4 символа.
    """
    if not value:
        return ""
    if mask_url:
        return value
    if len(value) <= 12:
        return value[:4] + "••••"
    return value[:6] + "••••••••" + value[-4:]


def _matrix_bot_mxid() -> str:
    """MXID бота из .env — подсказка в «Мои настройки» (без отдельной страницы привязки)."""
    return (os.getenv("MATRIX_USER_ID") or "").strip()


async def _matrix_bot_mxid_from_db(session: AsyncSession) -> str:
    """Читает MXID бота из БД (для Zero-Config режима)."""
    return await _load_secret_plain(session, "MATRIX_USER_ID")


async def _matrix_domain_from_db(session: AsyncSession) -> str:
    """Извлекает домен из MXID бота, сохраненного в БД."""
    mxid = await _matrix_bot_mxid_from_db(session)
    if ":" in mxid:
        return mxid.split(":", 1)[1]
    return ""


def _matrix_domain() -> str:
    """Извлекает домен из MXID бота: @bot:messenger.red-soft.ru → messenger.red-soft.ru.
    (Fallback на env для обратной совместимости, но в Zero-Config читается из БД)."""
    mxid = _matrix_bot_mxid()
    if ":" in mxid:
        return mxid.split(":", 1)[1]
    return ""


async def _get_matrix_domain_from_db(session: AsyncSession) -> str:
    """Читает домен из БД (для использования в роутах)."""
    mxid = await _load_secret_plain(session, "MATRIX_USER_ID")
    if ":" in mxid:
        return mxid.split(":", 1)[1]
    return _matrix_domain()  # Fallback на env


NOTIFY_TYPE_KEYS: list[str] = []
CATALOG_NOTIFY_SECRET = "__catalog_notify"
CATALOG_VERSIONS_SECRET = "__catalog_versions"
SERVICE_TIMEZONE_SECRET = "__service_timezone"
SERVICE_TIMEZONE_FALLBACK = "Europe/Moscow"

ADMIN_BOOTSTRAP_FIRST_ADMIN = os.getenv("ADMIN_BOOTSTRAP_FIRST_ADMIN", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_LOGIN_RE = re.compile(r"^[a-zA-Z0-9@._+-]{3,255}$")


def _normalize_service_timezone_name(value: str) -> str:
    tz_name = (value or "").strip()
    if tz_name and tz_name in set(_standard_timezone_options()):
        return tz_name
    return SERVICE_TIMEZONE_FALLBACK


def _admin_allowlist() -> frozenset[str]:
    raw = (os.getenv("ADMIN_LOGINS") or "").strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def _normalize_login(raw: str) -> str:
    return (raw or "").strip().lower()


def _login_allowed(login: str) -> bool:
    allow = _admin_allowlist()
    if not allow:
        return True
    return login in allow


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _generic_login_error() -> str:
    return "Неверный логин или пароль"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _admin_events_log_path() -> Path:
    raw = (os.getenv("ADMIN_EVENTS_LOG_PATH") or "").strip()
    if raw:
        return Path(raw)
    return _ROOT / "data" / "bot.log"


def _read_log_tail(path: Path, *, max_lines: int = 400, max_bytes: int = 256_000) -> str:
    try:
        if not path.is_file():
            return (
                f"Файл лога не найден: {path}\n"
                "Проверьте LOG_TO_FILE у бота, том data/ и переменную ADMIN_EVENTS_LOG_PATH."
            )
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            chunk = f.read().decode("utf-8", errors="replace")
        lines = chunk.splitlines()
        return "\n".join(lines[-max_lines:]) if lines else ""
    except OSError as e:
        return f"Не удалось прочитать лог: {e}"


def _admin_audit_log_path() -> Path | None:
    raw = (os.getenv("ADMIN_AUDIT_LOG_PATH") or "").strip()
    if raw.lower() in ("-", "none", "off", "false", "0"):
        return None
    if not raw:
        return _ROOT / "data" / "admin_audit.log"
    p = Path(raw)
    return p if p.is_absolute() else _ROOT / p


def _append_audit_file_line(message: str) -> None:
    path = _admin_audit_log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = admin_events_log_timestamp_now()
        line = f"{ts} [AUDIT] {(message or '').strip()}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        logger.warning("Не удалось записать файл аудита (%s): %s", path, e)


def _admin_events_log_scan_bytes() -> int:
    raw = (os.getenv("ADMIN_EVENTS_LOG_SCAN_BYTES") or str(8 * 1024 * 1024)).strip()
    try:
        n = int(raw)
    except ValueError:
        return 8 * 1024 * 1024
    return max(64 * 1024, min(n, 64 * 1024 * 1024))


def _read_events_log_scan(path: Path, *, max_bytes: int) -> tuple[str, bool]:
    """
    Читает файл событий целиком или хвост (если больше max_bytes).
    Возвращает (текст, truncated): при усечении первая строка может быть обрезана и отбрасывается.
    """
    try:
        if not path.is_file():
            return (
                f"Файл лога не найден: {path}\n"
                "Проверьте LOG_TO_FILE у бота, том data/ и переменную ADMIN_EVENTS_LOG_PATH.",
            ), False
        size = path.stat().st_size
        with path.open("rb") as f:
            if size <= max_bytes:
                data = f.read()
                truncated = False
            else:
                f.seek(max(0, size - max_bytes))
                data = f.read()
                truncated = True
        text = data.decode("utf-8", errors="replace")
        if truncated:
            nl = text.find("\n")
            if nl != -1 and nl + 1 < len(text):
                text = text[nl + 1 :]
        return text, truncated
    except OSError as e:
        return f"Не удалось прочитать лог: {e}", False


def _append_ops_to_events_log(message: str) -> None:
    """
    Дублирует операции Docker из панели в файл «Событий» (по умолчанию data/bot.log),
    чтобы страница /events показывала то же, что видит админ в UI (лог бота при этом не заменяется).
    """
    path: Path | None = None
    try:
        path = _admin_events_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = admin_events_log_timestamp_now()
        safe = (message or "").replace("\n", " ").replace("\r", " ").strip()[:800]
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} [ADMIN] {safe}\n")
    except OSError as e:
        logger.warning(
            "Не удалось дописать строку [ADMIN] в лог событий %s: %s",
            path or "(unknown)",
            e,
            exc_info=True,
        )


def _dash_events_tail_line_count(*, max_lines: int = 400) -> int:
    """Число непустых строк в хвосте лога событий (как на /events), без учёта отсутствующего файла."""
    path = _admin_events_log_path()
    if not path.is_file():
        return 0
    text = _read_log_tail(path, max_lines=max_lines)
    return sum(1 for line in text.splitlines() if line.strip())


async def _dashboard_counts(session: AsyncSession) -> dict[str, int]:
    user_count = int(
        (await session.execute(select(func.count()).select_from(BotUser))).scalar_one() or 0
    )
    group_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SupportGroup)
                .where(SupportGroup.name != GROUP_UNASSIGNED_NAME)
            )
        ).scalar_one()
        or 0
    )
    users_ungrouped = int(
        (
            await session.execute(
                select(func.count())
                .select_from(BotUser)
                .where(
                    or_(
                        BotUser.group_id.is_(None),
                        BotUser.group_id.in_(
                            select(SupportGroup.id).where(
                                SupportGroup.name == GROUP_UNASSIGNED_NAME
                            )
                        ),
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    return {
        "user_count": user_count,
        "group_count": group_count,
        "users_without_group": users_ungrouped,
        "events_tail_lines": _dash_events_tail_line_count(),
    }


def _parse_status_keys_list(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").replace("\n", ",").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _parse_json_string_list(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _default_notify_catalog() -> list[dict[str, str]]:
    return []


def _default_versions_catalog() -> list[str]:
    return []


def _catalog_key_from_label(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if not base:
        base = "opt"
    key = base
    i = 2
    while key in used:
        key = f"{base}_{i}"
        i += 1
    return key


def _normalize_notify_catalog(data) -> list[dict[str, str]]:
    if not isinstance(data, list):
        return _default_notify_catalog()
    out: list[dict[str, str]] = []
    used: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            key = str(item.get("key") or "").strip().lower()
        else:
            label = str(item).strip()
            key = ""
        if not label:
            continue
        if not key:
            key = _catalog_key_from_label(label, used)
        if key in used:
            continue
        used.add(key)
        out.append({"key": key, "label": label})
    return out


def _normalize_versions_catalog(data) -> list[str]:
    if not isinstance(data, list):
        return _default_versions_catalog()
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


async def _load_secret_plain(session: AsyncSession, name: str) -> str:
    q = await session.execute(select(AppSecret).where(AppSecret.name == name))
    row = q.scalar_one_or_none()
    if row is None:
        return ""
    key = load_master_key()
    try:
        return decrypt_secret(row.ciphertext, row.nonce, key)
    except SecurityError:
        logger.warning("secret_decrypt_failed name=%s", name)
        return ""


async def _upsert_secret_plain(session: AsyncSession, name: str, value: str) -> None:
    key = load_master_key()
    enc = encrypt_secret(value, key=key)
    q = await session.execute(select(AppSecret).where(AppSecret.name == name))
    row = q.scalar_one_or_none()
    if row is None:
        session.add(
            AppSecret(
                name=name, ciphertext=enc.ciphertext, nonce=enc.nonce, key_version=enc.key_version
            )
        )
        return
    row.ciphertext = enc.ciphertext
    row.nonce = enc.nonce
    row.key_version = enc.key_version


async def _load_catalogs(session: AsyncSession) -> tuple[list[dict[str, str]], list[str]]:
    raw_notify = await _load_secret_plain(session, CATALOG_NOTIFY_SECRET)
    raw_versions = await _load_secret_plain(session, CATALOG_VERSIONS_SECRET)
    if raw_notify:
        try:
            notify_catalog = _normalize_notify_catalog(json.loads(raw_notify))
        except json.JSONDecodeError:
            notify_catalog = _default_notify_catalog()
    else:
        notify_catalog = _default_notify_catalog()
    if raw_versions:
        try:
            versions_catalog = _normalize_versions_catalog(json.loads(raw_versions))
        except json.JSONDecodeError:
            versions_catalog = _default_versions_catalog()
    else:
        versions_catalog = _default_versions_catalog()
    return notify_catalog, versions_catalog


def _parse_catalog_payload(
    notify_raw: str, versions_raw: str
) -> tuple[list[dict[str, str]], list[str]]:
    if notify_raw:
        try:
            notify_catalog = _normalize_notify_catalog(json.loads(notify_raw))
        except json.JSONDecodeError:
            notify_catalog = _default_notify_catalog()
    else:
        notify_catalog = _default_notify_catalog()
    if versions_raw:
        try:
            versions_catalog = _normalize_versions_catalog(json.loads(versions_raw))
        except json.JSONDecodeError:
            versions_catalog = _default_versions_catalog()
    else:
        versions_catalog = _default_versions_catalog()
    return notify_catalog, versions_catalog


def _normalized_group_filter_key(name: str) -> str:
    """Нормализация имени для сравнения с подписью фильтра (без дублей «Все группы» в select)."""
    normalized = unicodedata.normalize("NFKC", name or "")
    compact_spaces = " ".join(normalized.replace("\u00a0", " ").split())
    return compact_spaces.strip().casefold()


def _group_excluded_from_assignable_lists(name: str | None) -> bool:
    if name is None:
        return False
    s = str(name).strip()
    if not s:
        return False
    if s == GROUP_UNASSIGNED_NAME:
        return True
    if _normalized_group_filter_key(s) == _normalized_group_filter_key(
        GROUP_USERS_FILTER_ALL_LABEL
    ):
        return True
    return False


def _groups_assignable(groups: list) -> list:
    return [
        g for g in groups if not _group_excluded_from_assignable_lists(getattr(g, "name", None))
    ]


def _is_reserved_support_group(row) -> bool:
    return row is not None and getattr(row, "name", None) == GROUP_UNASSIGNED_NAME


def _group_display_name(groups_by_id: dict, group_id: int | None) -> str:
    if group_id is None:
        return GROUP_UNASSIGNED_DISPLAY
    g = groups_by_id.get(group_id)
    if not g:
        return GROUP_UNASSIGNED_DISPLAY
    if g.name == GROUP_UNASSIGNED_NAME:
        return GROUP_UNASSIGNED_DISPLAY
    return g.name


_OPS_FLASH_MESSAGES: dict[str, str] = {
    "stop_ok": "Остановка бота выполнена. Если контейнер уже был выключен, состояние не менялось.",
    "stop_error": "Не удалось остановить бот. Проверьте DOCKER_HOST, docker-socket-proxy и имя сервиса (DOCKER_TARGET_SERVICE, метки compose).",
    "start_ok": "Бот запущен. Если он уже работал, ничего не изменилось.",
    "start_error": "Не удалось запустить бот. Проверьте Docker и настройки.",
    "restart_accepted": "Перезапуск бота запланирован (команда уходит в фоне).",
    "ops_commit_error": "Не удалось сохранить запись в журнал операций (БД). Состояние Docker смотрите в выводе compose / на дашборде.",
}

_OPS_FLASH_WITH_DETAIL = frozenset({"stop_error", "start_error", "ops_commit_error"})


def _truncate_ops_detail(s: str, max_len: int = 400) -> str:
    t = (s or "").replace("\n", " ").replace("\r", " ")
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _ops_flash_message(ops: str | None, detail: str | None = None) -> str | None:
    if not ops:
        return None
    key = ops.strip()
    base = _OPS_FLASH_MESSAGES.get(key)
    if not base:
        return None
    d = (detail or "").strip()
    if d and key in _OPS_FLASH_WITH_DETAIL:
        return f"{base} Подробнее: {d}"
    return base


def _ensure_csrf(request: Request) -> tuple[str, bool]:
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        return token, False
    return secrets.token_urlsafe(24), True


def _verify_csrf(request: Request, form_token: str = "") -> None:
    """Проверка double-submit CSRF: поле формы или заголовок X-CSRF-Token (для HTMX)."""
    token = (form_token or "").strip()
    if not token:
        token = request.headers.get("X-CSRF-Token", "").strip()
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not cookie_token or not token or token != cookie_token:
        raise HTTPException(status_code=400, detail="Некорректный CSRF токен")


def _verify_csrf_json(request: Request) -> None:
    """CSRF-проверка для JSON-endpoints (тестовое сообщение и т.п.)."""
    token = request.headers.get("X-CSRF-Token", "").strip()
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not cookie_token or not token or token != cookie_token:
        raise HTTPException(status_code=400, detail="Некорректный CSRF токен")


async def _audit_op(
    session: AsyncSession,
    action: str,
    status: str,
    actor_login: str | None = None,
    detail: str | None = None,
) -> None:
    row = BotOpsAudit(
        actor_login=(actor_login or "").strip().lower() or None,
        action=action,
        status=status,
        detail=(detail or "")[:2000] or None,
    )
    session.add(row)
    d = ((detail or "").replace("\n", " "))[:1800]
    parts = [f"op={action}", f"status={status}"]
    al = (actor_login or "").strip()
    if al:
        parts.append(f"actor={al}")
    if d:
        parts.append(f"detail={d}")
    _append_audit_file_line(" ".join(parts))
    logger.info(
        json.dumps(
            {
                "level": "AUDIT",
                "action": action,
                "status": status,
                "actor": actor_login or "",
                "detail": detail or "",
                "ts": _now_utc().isoformat(),
            },
            ensure_ascii=False,
        )
    )


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
logger = logging.getLogger("admin")


def _infer_crud_entity_id(entity_type: str, details: dict | None) -> int | None:
    """Числовой идентификатор сущности для индексации в bot_ops_audit (эвристика по типу)."""
    if not details:
        return None

    def gint(v: object) -> int | None:
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return None

    et = (entity_type or "").strip()
    if et == "bot_user":
        return gint(details.get("id"))
    if et == "group":
        return gint(details.get("id"))
    if et in ("group_version_route", "group_status_route"):
        return gint(details.get("group_id"))
    if et == "user_version_route":
        return gint(details.get("bot_user_id"))
    if et == "route/version_global":
        return gint(details.get("id"))
    if et == "self_settings":
        return gint(details.get("bot_user_id"))
    return None


async def _persist_admin_crud_audit(
    session: AsyncSession,
    request_actor,
    entity_type: str,
    crud_action: str,
    details: dict | None,
) -> None:
    actor_login = (getattr(request_actor, "login", None) or "").strip().lower() or None
    cleaned = sanitize_audit_details(details or {})
    entity_id = _infer_crud_entity_id(entity_type, details)
    et = (entity_type or "unknown")[:64]
    ca = (crud_action or "unknown")[:32]
    dj = json.dumps(cleaned, ensure_ascii=False) if cleaned else ""
    if len(dj) > 2000:
        dj = dj[:1997] + "..."
    aud = f"ADMIN_CRUD entity={et} action={ca} actor={actor_login or ''}"
    if entity_id is not None:
        aud += f" entity_id={entity_id}"
    if dj:
        aud += f" details={dj}"
    _append_audit_file_line(aud)
    logger.info(
        json.dumps(
            {
                "level": "AUDIT",
                "action": "ADMIN_CRUD",
                "status": "ok",
                "actor": actor_login or "",
                "entity_type": et,
                "crud_action": ca,
                "entity_id": entity_id,
                "details": cleaned,
                "ts": _now_utc().isoformat(),
            },
            ensure_ascii=False,
        )
    )
    if not want_admin_audit_crud_db():
        return
    row = BotOpsAudit(
        actor_login=actor_login,
        action="ADMIN_CRUD",
        status="ok",
        detail=None,
        entity_type=et or None,
        entity_id=entity_id,
        crud_action=ca or None,
        details_json=cleaned if cleaned else None,
    )
    session.add(row)


async def _maybe_log_admin_crud(
    session: AsyncSession,
    request_actor,
    entity_type: str,
    action: str,
    details: dict | None = None,
) -> None:
    if want_admin_events_log_crud():
        actor = actor_label_for_crud_log(request_actor)
        line = format_crud_line(entity_type, action, actor, details)
        _append_ops_to_events_log(line)
    await _persist_admin_crud_audit(session, request_actor, entity_type, action, details)


# Кэши и хелперы теперь в helpers.py — импортируем чтобы не было дубликатов
from admin.helpers import (  # noqa: E402
    _append_audit_file_line,
    _append_ops_to_events_log,
    _ensure_csrf,
    _has_admin,
    _integration_status_cache,
    _now_utc,
    _verify_csrf,
)


def _runtime_status_from_file() -> dict:
    p = Path(RUNTIME_STATUS_FILE)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


async def _integration_status(session: AsyncSession, use_cache: bool = True) -> dict:
    if use_cache:
        cached = _integration_status_cache.get("flag")
        if cached is not None:
            return cached
    rows = await session.execute(
        select(AppSecret.name).where(AppSecret.name.in_(REQUIRED_SECRET_NAMES))
    )
    names = {r[0] for r in rows.all()}
    missing = [name for name in REQUIRED_SECRET_NAMES if name not in names]
    status = {
        "configured": len(missing) == 0,
        "missing": missing,
    }
    _integration_status_cache["flag"] = status
    return status


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Auth для админки через DB-сессии после входа по логину и паролю.
    """

    async def dispatch(self, request: Request, call_next):
        p = request.url.path
        if p.startswith("/static/") or p == "/favicon.ico":
            return await call_next(request)
        if (
            p
            in (
                "/login",
                "/forgot-password",
                "/reset-password",
                "/health",
                "/health/live",
                "/health/ready",
                SETUP_PATH,
            )
            or p.startswith("/docs")
            or p
            in (
                "/openapi.json",
                "/redoc",
            )
        ):
            return await call_next(request)

        try:
            factory = get_session_factory()
            async with factory() as session:
                has_admin = await _has_admin(session)
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

                u = await session.execute(select(BotAppUser).where(BotAppUser.id == sess.user_id))
                user = u.scalar_one_or_none()
                if not user:
                    return RedirectResponse("/login", status_code=303)
                if sess.session_version != getattr(user, "session_version", 1):
                    return RedirectResponse("/login", status_code=303)

                # Sliding idle timeout: продлеваем активную сессию на каждый запрос.
                sess.expires_at = now + timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
                await session.flush()
                await session.commit()

                request.state.current_user = user
                request.state.integration_status = await _integration_status(session)
        except Exception:
            return RedirectResponse("/login", status_code=303)

        csrf_token, set_csrf_cookie = _ensure_csrf(request)
        request.state.csrf_token = csrf_token
        response = await call_next(request)
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


app.add_middleware(AuthMiddleware)

# ═══════════════════════════════════════════════════════════════════════════
# ROUTERS
# ═══════════════════════════════════════════════════════════════════════════

from admin.routes.auth import router as auth_router  # noqa: E402
from admin.routes.health import router as health_router  # noqa: E402
from admin.routes.ops import router as ops_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(ops_router)
from admin.routes.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
from admin.routes.events import router as events_router  # noqa: E402

app.include_router(events_router)
from admin.routes.settings import router as settings_router  # noqa: E402

app.include_router(settings_router)
from admin.routes.me import router as me_router  # noqa: E402

app.include_router(me_router)
from admin.routes.redmine import router as redmine_router  # noqa: E402

app.include_router(redmine_router)
from admin.routes.secrets import router as secrets_router  # noqa: E402

app.include_router(secrets_router)
from admin.routes.app_users import router as app_users_router  # noqa: E402

app.include_router(app_users_router)
from admin.routes.routes_mgmt import router as routes_mgmt_router  # noqa: E402

app.include_router(routes_mgmt_router)
from admin.routes.groups import router as groups_router  # noqa: E402

app.include_router(groups_router)
from admin.routes.users import router as users_router  # noqa: E402

app.include_router(users_router)


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD UTILITIES (used by routes/dashboard.py via late import)
# ═══════════════════════════════════════════════════════════════════════════


def _restart_in_background(actor_login: str | None) -> None:
    def _run() -> None:
        time.sleep(1.5)
        detail = ""
        status = "ok"
        try:
            control_service("restart")
            detail = "restart command accepted"
        except Exception as e:  # noqa: BLE001
            status = "error"
            detail = str(e)

        async def _persist() -> None:
            factory = get_session_factory()
            async with factory() as s:
                await _audit_op(s, "BOT_RESTART", status, actor_login=actor_login, detail=detail)
                await s.commit()

        try:
            asyncio.run(_persist())
        except Exception:
            logger.exception("failed to persist restart audit")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# --- Bot Heartbeat API and other endpoints moved to routes/users.py ---


# ── Shared helpers (used by routes/users.py and routes/groups.py via late import) ──


def _parse_notify(raw: str) -> list:
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else ["all"]
    except json.JSONDecodeError:
        return ["all"]


def _normalize_notify(values: list[str] | None, allowed_keys: list[str] | None = None) -> list[str]:
    vals = [v.strip() for v in (values or []) if v and v.strip()]
    if not vals:
        return ["all"]
    if "all" in vals:
        return ["all"]
    allowed_set = set(allowed_keys or NOTIFY_TYPE_KEYS)
    allowed = [v for v in vals if v in allowed_set]
    return allowed or ["all"]


def _notify_preset(notify: list | None) -> str:
    values = [str(x).strip() for x in (notify or []) if str(x).strip()]
    if not values or "all" in values:
        return "all"
    return "custom"


def _parse_work_days(raw: str) -> list[int] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else None
    except json.JSONDecodeError:
        return None


def _parse_work_hours_range(value: str) -> tuple[str, str]:
    if not value or "-" not in value:
        return "", ""
    start, end = value.split("-", 1)
    return start.strip(), end.strip()


def _normalize_versions(
    values: list[str] | None, allowed_values: list[str] | None = None
) -> list[str]:
    vals = [v.strip() for v in (values or []) if v and v.strip()]
    if not vals:
        return []
    allowed_set = set(allowed_values or [])
    if not allowed_set:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in vals:
        if v in seen or v not in allowed_set:
            continue
        seen.add(v)
        out.append(v)
    return out


def _version_preset(selected: list[str] | None, catalog: list[str] | None) -> str:
    selected_list = [str(x).strip() for x in (selected or []) if str(x).strip()]
    if not selected_list:
        return "all"
    return "custom"


# --- Matrix helpers (used by routes/users.py and routes/groups.py via late import) ---


async def _get_matrix_client(session: AsyncSession) -> AsyncClient | None:
    """
    Создает и настраивает Matrix-клиент на основе секретов из БД.
    Возвращает None, если секреты не настроены.
    """
    homeserver = await _load_secret_plain(session, "MATRIX_HOMESERVER")
    access_token = await _load_secret_plain(session, "MATRIX_ACCESS_TOKEN")
    bot_mxid = await _load_secret_plain(session, "MATRIX_USER_ID")

    if not all([homeserver, access_token, bot_mxid]):
        return None

    from nio import AsyncClient

    client = AsyncClient(homeserver, bot_mxid)
    client.access_token = access_token
    client.device_id = "redmine_bot_admin"
    client.restore_login(bot_mxid, "redmine_bot_admin", access_token)
    return client


async def _sync_matrix_client(client: AsyncClient, timeout: int = 10000) -> bool:
    """Синхронизирует клиент. Возвращает True при успехе."""
    try:
        await client.sync(timeout=timeout)
        return True
    except Exception:
        return False


# --- Room helpers (used by routes/users.py via late import) ---


def _room_localpart(room_id: str) -> str:
    """Извлекает localpart из room_id: !xxxxxx:server -> xxxxxx"""
    if not room_id:
        return ""
    if room_id.startswith("!") and ":" in room_id:
        return room_id[1:].split(":", 1)[0]
    return room_id


async def _build_room_id_async(localpart: str, session: AsyncSession) -> str:
    """Конструирует полный room_id из localpart + домен бота (читая домен из БД)."""
    domain = await _matrix_domain_from_db(session)
    if not localpart or not domain:
        return localpart
    if localpart.startswith("!"):
        return localpart
    if localpart.startswith("@"):
        return f"{localpart.split(':', 1)[0]}:{domain}" if ":" not in localpart else localpart
    return f"!{localpart}:{domain}"


# ═══════════════════════════════════════════════════════════════════════════
# DB credentials management (zero-config deployment)
# ═══════════════════════════════════════════════════════════════════════════

# Путь к .env файлу в Docker-контейнере
_ENV_FILE_PATH = Path("/app/.env")


def _load_db_config_from_env() -> dict[str, str]:
    """Читает DB credentials из .env файла."""
    if not _ENV_FILE_PATH.exists():
        return {
            "postgres_user": "bot",
            "postgres_db": "via",
            "postgres_password": "",
            "app_master_key": "",
        }

    config = {}
    for line in _ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    return {
        "postgres_user": config.get("POSTGRES_USER", "bot"),
        "postgres_db": config.get("POSTGRES_DB", "via"),
        "postgres_password": config.get("POSTGRES_PASSWORD", ""),
        "app_master_key": config.get("APP_MASTER_KEY", ""),
    }


def _update_env_file(updates: dict[str, str]) -> None:
    """Обновляет переменные в .env файле, сохраняя остальные."""
    if not _ENV_FILE_PATH.exists():
        raise RuntimeError(".env file not found")

    lines = _ENV_FILE_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated_keys = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Добавляем новые ключи, которых не было в файле
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    _ENV_FILE_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/settings/db-config", response_class=JSONResponse)
async def get_db_config(request: Request, session: AsyncSession = Depends(get_session)):
    """Возвращает текущие DB credentials из .env (только для admin)."""
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    config = _load_db_config_from_env()
    return {
        "ok": True,
        "postgres_user": config["postgres_user"],
        "postgres_db": config["postgres_db"],
        "postgres_password": config["postgres_password"],
        "app_master_key": config["app_master_key"],
    }


@app.post("/settings/db-config/regenerate", response_class=JSONResponse)
async def regenerate_db_config(
    request: Request,
    regenerate_password: Annotated[str, Form()] = "1",
    regenerate_key: Annotated[str, Form()] = "1",
    csrf_token: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
):
    """
    Генерирует новые credentials и обновляет .env.

    После вызова необходимо перезапустить контейнеры bot и admin,
    чтобы они подхватили новые credentials.

    PostgreSQL пароль также обновляется через ALTER USER.
    """
    import secrets as _secrets

    _verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    current_config = _load_db_config_from_env()
    updates = {}

    # Генерируем новые credentials
    if regenerate_password in ("1", "true", "yes", "on"):
        updates["POSTGRES_PASSWORD"] = _secrets.token_urlsafe(32)

    if regenerate_key in ("1", "true", "yes", "on"):
        updates["APP_MASTER_KEY"] = _secrets.token_urlsafe(32)

    if not updates:
        raise HTTPException(400, "Нечего перегенерировать")

    # Обновляем .env файл
    _update_env_file(updates)

    # Обновляем пароль в PostgreSQL
    if "POSTGRES_PASSWORD" in updates:
        try:
            from sqlalchemy import text

            # Подключаемся к БД с текущими credentials и меняем пароль
            await session.execute(
                text("ALTER USER :username WITH PASSWORD :password"),
                {
                    "username": current_config["postgres_user"],
                    "password": updates["POSTGRES_PASSWORD"],
                },
            )
            await session.commit()
        except Exception as e:
            # Откатываем изменения в .env при ошибке
            _update_env_file(
                {
                    k: current_config[k.replace("POSTGRES_", "").lower()]
                    for k in updates
                    if k in current_config
                }
            )
            raise HTTPException(500, f"Не удалось обновить пароль в PostgreSQL: {e}") from e

    logger.info(
        "db_credentials_regenerated actor=%s regenerated=%s",
        mask_identifier(user.login),
        list(updates.keys()),
    )

    return {
        "ok": True,
        "message": "Credentials обновлены. Перезапустите контейнеры: docker compose restart postgres bot admin",
        "regenerated": list(updates.keys()),
        "new_postgres_password": updates.get("POSTGRES_PASSWORD", ""),
        "new_app_master_key": updates.get("APP_MASTER_KEY", ""),
    }
