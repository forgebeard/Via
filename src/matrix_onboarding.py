"""
Онбординг подписчиков через личку Matrix: state machine + запись в bot_users.

Секреты не логируем; тело сообщения с API-ключом не попадает в логи.
После успешной обработки ключа — попытка redaction события (если позволяет PL).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotUser, OnboardingSession, SupportGroup
from database.session import get_session_factory
from security import SecurityError, encrypt_secret

logger = logging.getLogger("redmine_bot")

# Служебная группа — не назначать через бот
_GROUP_UNASSIGNED = "UNASSIGNED"

STEP_AWAIT_KEY = "await_key"
STEP_AWAIT_DEPT = "await_dept"
STEP_AWAIT_HOURS = "await_hours"
STEP_AWAIT_DAYS = "await_days"
STEP_AWAIT_NOTIFY = "await_notify"

NOTIFY_KEYS = (
    "new",
    "info",
    "reminder",
    "overdue",
    "status_change",
    "issue_updated",
    "reopened",
)

_WELCOME = """Привет! Я бот уведомлений Redmine.

Чтобы подписаться, отправьте команду **!start** (настройка по шагам).

Команды: **!help** — справка, **!cancel** — отменить, **!status** — текущий шаг, **!change** — изменить настройки (если уже подключены).

⚠️ API-ключ Redmine остаётся в истории чата Matrix — при возможности удалите сообщение с ключом сами после настройки."""

_HELP = """**Команды**
• !start — начать подписку
• !cancel — отменить и начать заново позже
• !status — на каком вы шаге
• !change — сменить отдел / часы / дни / уведомления (без смены ключа)
• !help — эта справка

**Redmine ID** виден в URL профиля: `/users/123` → ID = 123.

**Дни недели:** числа 0–6 через запятую (0 = пн, 6 = вс). По умолчанию 0,1,2,3,4.

**Часы:** интервал `09:00-18:00` (МСК / таймзона бота). По умолчанию 09:00-18:00.

**Уведомления:** `all` или список через запятую: new, info, reminder, overdue, status_change, issue_updated, reopened."""


@dataclass
class OnboardingRuntime:
    master_key: bytes
    redmine_url: str
    reload_users: Callable[[], Awaitable[None]]
    bot_matrix_user_id: str
    session_ttl_seconds: int


_CTX: OnboardingRuntime | None = None


def configure_onboarding(ctx: OnboardingRuntime | None) -> None:
    global _CTX
    _CTX = ctx


def onboarding_enabled() -> bool:
    return _CTX is not None


def _norm_cmd(text: str) -> str:
    return (text or "").strip().lower()


def _redmine_current_user_sync(url: str, api_key: str) -> tuple[dict | None, str | None]:
    """GET users/current.json. Не логировать ключ."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return None, "no_url"
    req = urllib.request.Request(
        f"{base}/users/current.json",
        headers={"X-Redmine-API-Key": (api_key or "").strip()},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        user = data.get("user")
        if not isinstance(user, dict):
            return None, "bad_response"
        return user, None
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}"
    except Exception:
        logger.exception("onboarding: Redmine request failed (no body logged)")
        return None, "request_error"


async def validate_redmine_api_key(redmine_url: str, api_key: str) -> tuple[dict | None, str | None]:
    return await asyncio.to_thread(_redmine_current_user_sync, redmine_url, api_key)


def _parse_work_hours(text: str) -> tuple[str | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return "09:00-18:00", None
    m = re.match(r"^\s*(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})\s*$", raw)
    if not m:
        return None, "Формат: 09:00-18:00"
    return f"{m.group(1)}-{m.group(2)}", None


def _parse_work_days(text: str) -> tuple[list[int] | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return [0, 1, 2, 3, 4], None
    parts = re.split(r"[\s,;]+", raw)
    days: set[int] = set()
    for p in parts:
        if not p:
            continue
        if not p.isdigit():
            return None, "Укажите дни числами 0–6 через запятую (0 = пн)."
        d = int(p)
        if d < 0 or d > 6:
            return None, "День должен быть от 0 (пн) до 6 (вс)."
        days.add(d)
    if not days:
        return [0, 1, 2, 3, 4], None
    return sorted(days), None


def _parse_notify(text: str) -> tuple[list[str] | None, str | None]:
    raw = (text or "").strip().lower()
    if not raw or raw in ("all", "все", "всё"):
        return ["all"], None
    parts = [p.strip() for p in re.split(r"[\s,;]+", raw) if p.strip()]
    out: list[str] = []
    for p in parts:
        if p not in NOTIFY_KEYS:
            return None, f"Неизвестный тип «{p}». Допустимо: all или {', '.join(NOTIFY_KEYS)}."
        out.append(p)
    if not out:
        return ["all"], None
    if "all" in out:
        return ["all"], None
    return out, None


async def _is_likely_dm(client, room_id: str) -> bool:
    from nio import JoinedMembersError

    resp = await client.joined_members(room_id)
    if isinstance(resp, JoinedMembersError):
        logger.debug("onboarding: joined_members error room=%s", room_id)
        return False
    n = len(resp.members or [])
    return n <= 2


async def _send_text(client, room_id: str, body: str) -> None:
    from matrix_send import room_send_with_retry

    await room_send_with_retry(
        client,
        room_id,
        {
            "msgtype": "m.text",
            "body": body,
            "format": "org.matrix.custom.html",
            "formatted_body": body.replace("\n", "<br/>"),
        },
    )


async def _try_redact(client, room_id: str, event_id: str | None) -> None:
    if not event_id:
        return
    try:
        await client.room_redact(room_id, event_id, reason="onboarding")
    except Exception:
        logger.debug("onboarding: redact skipped room=%s", room_id, exc_info=True)


async def _load_session(session: AsyncSession, room_id: str) -> OnboardingSession | None:
    r = await session.execute(select(OnboardingSession).where(OnboardingSession.room_id == room_id))
    return r.scalar_one_or_none()


async def _delete_session(session: AsyncSession, row: OnboardingSession | None) -> None:
    if row:
        await session.delete(row)


def _session_expired(row: OnboardingSession, ttl: int) -> bool:
    now = datetime.now(timezone.utc)
    if row.updated_at.tzinfo is None:
        updated = row.updated_at.replace(tzinfo=timezone.utc)
    else:
        updated = row.updated_at
    return (now - updated) > timedelta(seconds=ttl)


async def handle_matrix_message(
    client,
    room_id: str,
    sender_mxid: str,
    body: str,
    event_id: str | None = None,
) -> None:
    if _CTX is None:
        return
    if sender_mxid == _CTX.bot_matrix_user_id:
        return

    if not await _is_likely_dm(client, room_id):
        return

    cmd = _norm_cmd(body)
    factory = get_session_factory()

    async with factory() as session:
        row = await _load_session(session, room_id)
        if row and _session_expired(row, _CTX.session_ttl_seconds):
            await _delete_session(session, row)
            row = None
            await session.commit()
            await _send_text(
                client,
                room_id,
                "Сессия настройки истекла. Напишите **!start**, чтобы начать снова.",
            )
            await session.commit()
            return

        if cmd in ("!help", "/help"):
            await _send_text(client, room_id, _HELP)
            await session.commit()
            return

        if cmd in ("!cancel", "/cancel"):
            if row:
                await _delete_session(session, row)
                await session.commit()
            await _send_text(client, room_id, "Настройка отменена. Когда будете готовы — **!start**.")
            return

        if cmd in ("!status", "/status"):
            if not row:
                await _send_text(client, room_id, "Активной настройки нет. **!start** — начать.")
            else:
                await _send_text(client, room_id, f"Текущий шаг: `{row.step}`. **!cancel** — сброс.")
            await session.commit()
            return

        if cmd in ("!change", "/change"):
            existing = await session.execute(select(BotUser).where(BotUser.room == room_id))
            bu = existing.scalar_one_or_none()
            if not bu:
                await _send_text(
                    client,
                    room_id,
                    "Запись для этой комнаты не найдена. Сначала **!start**.",
                )
                await session.commit()
                return
            if row:
                await _delete_session(session, row)
            session.add(
                OnboardingSession(
                    room_id=room_id,
                    sender_mxid=sender_mxid,
                    step=STEP_AWAIT_DEPT,
                    redmine_id=bu.redmine_id,
                    api_key_ciphertext=bu.redmine_api_key_ciphertext,
                    api_key_nonce=bu.redmine_api_key_nonce,
                    change_mode=True,
                    existing_bot_user_id=bu.id,
                )
            )
            await session.commit()
            await _send_text(
                client,
                room_id,
                "Режим изменения настроек (ключ не меняем).\n\n"
                "Введите **название отдела** (как в панели «Группы»).",
            )
            return

        if cmd in ("!start", "/start") or (not row and not cmd.startswith("!")):
            if not row and cmd not in ("!start", "/start"):
                await _send_text(client, room_id, _WELCOME)
                await session.commit()
                return

            if row and cmd in ("!start", "/start"):
                await _delete_session(session, row)
                row = None

            if cmd in ("!start", "/start"):
                session.add(
                    OnboardingSession(
                        room_id=room_id,
                        sender_mxid=sender_mxid,
                        step=STEP_AWAIT_KEY,
                    )
                )
                await session.commit()
                await _send_text(
                    client,
                    room_id,
                    "Шаг 1/5: пришлите **API-ключ Redmine** одним сообщением.\n\n"
                    "⚠️ Ключ попадёт в историю чата; после настройки при возможности **удалите** это сообщение. "
                    "Ключ хранится у нас зашифрованным.\n\n"
                    "**!cancel** — отмена.",
                )
                return

        if not row:
            await session.commit()
            return

        # Дальше — шаги с текстом (не команды верхнего уровня)
        if cmd.startswith("!"):
            await _send_text(client, room_id, "Неизвестная команда. **!help**")
            await session.commit()
            return

        if row.step == STEP_AWAIT_KEY:
            key = (body or "").strip()
            if len(key) < 8 or len(key) > 256:
                await _send_text(client, room_id, "Ключ слишком короткий или длинный. Попробуйте снова или **!cancel**.")
                await session.commit()
                return
            user, err = await validate_redmine_api_key(_CTX.redmine_url, key)
            if err or not user:
                logger.warning("onboarding: key validation failed hint=%s room=%s", err, room_id)
                await _send_text(
                    client,
                    room_id,
                    "Не удалось проверить ключ в Redmine. Проверьте ключ и URL сервера. **!cancel**",
                )
                await session.commit()
                return
            try:
                enc = encrypt_secret(key, _CTX.master_key)
            except SecurityError:
                logger.error("onboarding: master key missing or invalid for encrypt")
                await _send_text(client, room_id, "Ошибка шифрования на сервере. Обратитесь к администратору.")
                await session.commit()
                return
            rid = int(user["id"])
            row.api_key_ciphertext = enc.ciphertext
            row.api_key_nonce = enc.nonce
            row.redmine_id = rid
            row.step = STEP_AWAIT_DEPT
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("onboarding: key accepted redmine_id=%s room=%s", rid, room_id)
            await _try_redact(client, room_id, event_id)
            fn = (user.get("firstname") or "").strip()
            ln = (user.get("lastname") or "").strip()
            disp = (f"{fn} {ln}".strip() or user.get("login") or "").strip()
            # Временно держим display_name в department_name col? Use draft - store in department_name prefix NO
            # store in session: reuse department_name for display is wrong. Add note in message only.
            welcome_name = f" ({disp})" if disp else ""
            await _send_text(
                client,
                room_id,
                f"Ключ принят{welcome_name}. Redmine ID: **{rid}**.\n\n"
                "Шаг 2/5: введите **название отдела** (как группа в панели бота, без учёта регистра).",
            )
            return

        if row.step == STEP_AWAIT_DEPT:
            name = (body or "").strip()
            if not name:
                await _send_text(client, room_id, "Введите непустое название отдела.")
                await session.commit()
                return
            if name.upper() == _GROUP_UNASSIGNED:
                await _send_text(client, room_id, "Эта группа зарезервирована. Укажите другой отдел.")
                await session.commit()
                return
            r = await session.execute(
                select(SupportGroup).where(func.lower(SupportGroup.name) == func.lower(name))
            )
            g = r.scalar_one_or_none()
            if not g or not g.is_active:
                await _send_text(
                    client,
                    room_id,
                    "Группа не найдена или неактивна. Проверьте название или попросите админа создать группу в панели.",
                )
                await session.commit()
                return
            row.department_name = g.name
            row.step = STEP_AWAIT_HOURS
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await _send_text(
                client,
                room_id,
                "Шаг 3/5: **рабочие часы** для тихих уведомлений (формат `09:00-18:00`) или напишите **пропуск** для значения по умолчанию.",
            )
            return

        if row.step == STEP_AWAIT_HOURS:
            t = (body or "").strip().lower()
            if t in ("пропуск", "skip", "-", "default"):
                wh = "09:00-18:00"
            else:
                wh, err = _parse_work_hours(body)
                if err:
                    await _send_text(client, room_id, err)
                    await session.commit()
                    return
            row.work_hours = wh
            row.step = STEP_AWAIT_DAYS
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await _send_text(
                client,
                room_id,
                "Шаг 4/5: **дни недели** (0=пн … 6=вс), через запятую, или **пропуск** для пн–пт.",
            )
            return

        if row.step == STEP_AWAIT_DAYS:
            t = (body or "").strip().lower()
            if t in ("пропуск", "skip", "-", "default"):
                wd = [0, 1, 2, 3, 4]
            else:
                wd, err = _parse_work_days(body)
                if err:
                    await _send_text(client, room_id, err)
                    await session.commit()
                    return
            row.work_days = wd
            row.step = STEP_AWAIT_NOTIFY
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await _send_text(
                client,
                room_id,
                "Шаг 5/5: **уведомления** — `all` или список: new, overdue, … (см. **!help**). **пропуск** = all.",
            )
            return

        if row.step == STEP_AWAIT_NOTIFY:
            t = (body or "").strip().lower()
            if t in ("пропуск", "skip", "-", "default"):
                nf = ["all"]
            else:
                nf, err = _parse_notify(body)
                if err:
                    await _send_text(client, room_id, err)
                    await session.commit()
                    return

            assert row.redmine_id is not None
            rid = int(row.redmine_id)

            existing_q = await session.execute(select(BotUser).where(BotUser.redmine_id == rid))
            existing = existing_q.scalar_one_or_none()

            if existing and existing.room.strip() != room_id.strip():
                await _send_text(
                    client,
                    room_id,
                    "Этот пользователь Redmine уже привязан к **другой** Matrix-комнате. Обратитесь к администратору.",
                )
                await session.commit()
                return

            gname = row.department_name or ""
            gr = await session.execute(
                select(SupportGroup).where(func.lower(SupportGroup.name) == func.lower(gname))
            )
            g = gr.scalar_one_or_none()
            if not g:
                await _send_text(client, room_id, "Внутренняя ошибка: группа не найдена. **!start** сначала.")
                await session.commit()
                return

            if row.change_mode and row.existing_bot_user_id:
                bu = await session.get(BotUser, row.existing_bot_user_id)
                if not bu or bu.room.strip() != room_id.strip():
                    await _send_text(client, room_id, "Запись пользователя не совпадает с комнатой. Обратитесь к администратору.")
                    await session.commit()
                    return
                bu.group_id = g.id
                bu.department = g.name
                bu.work_hours = row.work_hours
                bu.work_days = row.work_days
                bu.notify = nf
                bu.redmine_api_key_ciphertext = row.api_key_ciphertext
                bu.redmine_api_key_nonce = row.api_key_nonce
            elif existing:
                existing.room = room_id
                existing.group_id = g.id
                existing.department = g.name
                existing.work_hours = row.work_hours
                existing.work_days = row.work_days
                existing.notify = nf
                existing.redmine_api_key_ciphertext = row.api_key_ciphertext
                existing.redmine_api_key_nonce = row.api_key_nonce
            else:
                bu_new = BotUser(
                    redmine_id=rid,
                    display_name=None,
                    group_id=g.id,
                    department=g.name,
                    room=room_id,
                    notify=nf,
                    work_hours=row.work_hours,
                    work_days=row.work_days,
                    dnd=False,
                    redmine_api_key_ciphertext=row.api_key_ciphertext,
                    redmine_api_key_nonce=row.api_key_nonce,
                )
                session.add(bu_new)

            was_change = row.change_mode
            await _delete_session(session, row)
            await session.commit()
            logger.info("onboarding: completed redmine_id=%s room=%s change=%s", rid, room_id, was_change)

            await _CTX.reload_users()
            await _send_text(
                client,
                room_id,
                "Готово. Настройки сохранены; уведомления пойдут в эту комнату. "
                "Изменить снова: **!change**. Справка: **!help**.",
            )
            return

        await session.commit()

