"""Catalog routes: справочник статусов, версий и приоритетов Redmine."""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database.models import BotUser, RedminePriority, RedmineStatus, RedmineVersion, SupportGroup
from database.session import get_session

logger = logging.getLogger("catalog")

router = APIRouter(tags=["catalog"])

REQUEST_TIMEOUT = 15


def _admin() -> object:
    import admin.main as _m

    return _m


# ── GET /api/catalog/statuses ───────────────────────────────────────


@router.get("/api/catalog/statuses")
async def catalog_statuses_list(
    request: Request,
    session=Depends(get_session),
):
    """Список всех статусов из БД (активных и скрытых)."""
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    result = await session.execute(select(RedmineStatus).order_by(RedmineStatus.id))
    statuses = result.scalars().all()

    return JSONResponse(
        {
            "statuses": [
                {
                    "id": s.id,
                    "redmine_status_id": s.redmine_status_id,
                    "name": s.name,
                    "is_active": s.is_active,
                    "is_closed": s.is_closed,
                    "is_default": s.is_default,
                }
                for s in statuses
            ]
        }
    )


# ── POST /api/catalog/statuses ──────────────────────────────────────


@router.post("/api/catalog/statuses")
async def catalog_statuses_create(
    request: Request,
    redmine_status_id: Annotated[int, Form()],
    name: Annotated[str, Form()],
    is_closed: Annotated[bool, Form()] = False,
    csrf_token: Annotated[str, Form()] = "",
    session=Depends(get_session),
):
    """Добавить статус вручную."""
    admin = _admin()
    admin._verify_csrf(request, csrf_token)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    # Проверяем дубликат
    existing = await session.execute(
        select(RedmineStatus).where(RedmineStatus.redmine_status_id == redmine_status_id)
    )
    if existing.scalar_one_or_none():
        return JSONResponse({"error": "Статус с таким ID уже существует"}, status_code=409)

    row = RedmineStatus(
        redmine_status_id=redmine_status_id,
        name=name.strip(),
        is_closed=is_closed,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return JSONResponse(
        {
            "id": row.id,
            "redmine_status_id": row.redmine_status_id,
            "name": row.name,
            "is_closed": row.is_closed,
        }
    )


# ── POST /api/catalog/statuses/{status_id}/toggle ──────────────────


@router.post("/api/catalog/statuses/{status_id}/toggle")
async def catalog_statuses_toggle(
    request: Request,
    status_id: int,
    field: str = "is_active",
    session=Depends(get_session),
):
    """Переключить is_active или is_default."""
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedmineStatus, status_id)
    if not row:
        return JSONResponse({"error": "Статус не найден"}, status_code=404)

    if field == "is_active":
        row.is_active = not row.is_active
    elif field == "is_default":
        row.is_default = not row.is_default
    else:
        return JSONResponse({"error": "Неверное поле"}, status_code=400)

    await session.commit()

    return JSONResponse(
        {
            "ok": True,
            "is_active": row.is_active,
            "is_default": row.is_default,
        }
    )


# ── DELETE /api/catalog/statuses/{status_id} ────────────────────────


@router.delete("/api/catalog/statuses/{status_id}")
async def catalog_statuses_delete(
    request: Request,
    status_id: int,
    session=Depends(get_session),
):
    """Удалить статус навсегда.

    Каскадно удаляет из BotUser.notify и SupportGroup.notify.
    """
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedmineStatus, status_id)
    if not row:
        return JSONResponse({"error": "Статус не найден"}, status_code=404)

    status_key = str(row.redmine_status_id)

    # Удаляем статус из notify всех пользователей
    all_users = await session.execute(select(BotUser))
    affected_users = 0
    for u in all_users.scalars().all():
        if u.notify and status_key in u.notify:
            u.notify = [s for s in u.notify if s != status_key]
            affected_users += 1
            await session.flush()

    # Удаляем статус из notify всех групп
    all_groups = await session.execute(select(SupportGroup))
    affected_groups = 0
    for g in all_groups.scalars().all():
        if g.notify and status_key in g.notify:
            g.notify = [s for s in g.notify if s != status_key]
            affected_groups += 1
            await session.flush()

    await session.delete(row)
    await session.commit()

    return JSONResponse(
        {
            "ok": True,
            "affected_users": affected_users,
            "affected_groups": affected_groups,
        }
    )


# ── GET /api/catalog/versions ───────────────────────────────────────


@router.get("/api/catalog/versions")
async def catalog_versions_list(
    request: Request,
    session=Depends(get_session),
):
    """Список всех версий из БД."""
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    result = await session.execute(select(RedmineVersion).order_by(RedmineVersion.id))
    versions = result.scalars().all()

    return JSONResponse(
        {
            "versions": [
                {
                    "id": v.id,
                    "redmine_version_id": v.redmine_version_id,
                    "name": v.name,
                    "is_active": v.is_active,
                    "is_default": v.is_default,
                }
                for v in versions
            ]
        }
    )


# ── POST /api/catalog/versions/{version_id}/toggle ──────────────────


@router.post("/api/catalog/versions/{version_id}/toggle")
async def catalog_versions_toggle(
    request: Request,
    version_id: int,
    field: str = "is_active",
    session=Depends(get_session),
):
    """Переключить is_active или is_default для версии."""
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedmineVersion, version_id)
    if not row:
        return JSONResponse({"error": "Версия не найдена"}, status_code=404)

    if field == "is_active":
        row.is_active = not row.is_active
    elif field == "is_default":
        row.is_default = not row.is_default
    else:
        return JSONResponse({"error": "Неверное поле"}, status_code=400)

    await session.commit()
    return JSONResponse({"ok": True, "is_active": row.is_active, "is_default": row.is_default})


# ── DELETE /api/catalog/versions/{version_id} ───────────────────────


@router.delete("/api/catalog/versions/{version_id}")
async def catalog_versions_delete(
    request: Request,
    version_id: int,
    session=Depends(get_session),
):
    """Удалить версию навсегда."""
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedmineVersion, version_id)
    if not row:
        return JSONResponse({"error": "Версия не найдена"}, status_code=404)

    await session.delete(row)
    await session.commit()
    return JSONResponse({"ok": True})


# ── GET /api/catalog/priorities ─────────────────────────────────────


@router.get("/api/catalog/priorities")
async def catalog_priorities_list(
    request: Request,
    session=Depends(get_session),
):
    """Список всех приоритетов из БД."""
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    result = await session.execute(select(RedminePriority).order_by(RedminePriority.id))
    priorities = result.scalars().all()

    return JSONResponse(
        {
            "priorities": [
                {
                    "id": p.id,
                    "redmine_priority_id": p.redmine_priority_id,
                    "name": p.name,
                    "is_active": p.is_active,
                    "is_default": p.is_default,
                }
                for p in priorities
            ]
        }
    )


# ── POST /api/catalog/priorities/{priority_id}/toggle ───────────────


@router.post("/api/catalog/priorities/{priority_id}/toggle")
async def catalog_priorities_toggle(
    request: Request,
    priority_id: int,
    field: str = "is_active",
    session=Depends(get_session),
):
    """Переключить is_active или is_default для приоритета."""
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedminePriority, priority_id)
    if not row:
        return JSONResponse({"error": "Приоритет не найден"}, status_code=404)

    if field == "is_active":
        row.is_active = not row.is_active
    elif field == "is_default":
        row.is_default = not row.is_default
    else:
        return JSONResponse({"error": "Неверное поле"}, status_code=400)

    await session.commit()
    return JSONResponse({"ok": True, "is_active": row.is_active, "is_default": row.is_default})


# ── DELETE /api/catalog/priorities/{priority_id} ────────────────────


@router.delete("/api/catalog/priorities/{priority_id}")
async def catalog_priorities_delete(
    request: Request,
    priority_id: int,
    session=Depends(get_session),
):
    """Удалить приоритет навсегда."""
    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    row = await session.get(RedminePriority, priority_id)
    if not row:
        return JSONResponse({"error": "Приоритет не найден"}, status_code=404)

    await session.delete(row)
    await session.commit()
    return JSONResponse({"ok": True})


# ── POST /api/catalog/sync-all ──────────────────────────────────────


@router.post("/api/catalog/sync-all")
async def catalog_sync_all(
    request: Request,
    session=Depends(get_session),
):
    """Синхронизировать статусы, версии и приоритеты из Redmine API."""
    from admin.helpers_ext import _load_secret_plain

    admin = _admin()
    admin._verify_csrf_json(request)
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")

    redmine_url = await _load_secret_plain(session, "REDMINE_URL")
    redmine_key = await _load_secret_plain(session, "REDMINE_API_KEY")

    if not redmine_url or not redmine_key:
        return JSONResponse(
            {"error": "Заполните параметры Redmine (URL и API key)"}, status_code=400
        )

    headers = {"X-Redmine-API-Key": redmine_key}
    base_url = redmine_url.rstrip("/")

    results = {
        "statuses": {"added": 0, "updated": 0, "hidden": 0},
        "versions": {"added": 0, "updated": 0, "hidden": 0},
        "priorities": {"added": 0, "updated": 0, "hidden": 0},
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        # ── 1. Sync Statuses ─────────────────────────────────────────
        try:
            resp = await client.get(f"{base_url}/issue_statuses.json", headers=headers)
            resp.raise_for_status()
            redmine_statuses = resp.json().get("issue_statuses", [])

            result = await session.execute(select(RedmineStatus).where(RedmineStatus.is_active))
            db_statuses = {s.redmine_status_id: s for s in result.scalars().all()}

            redmine_ids = set()
            for rs in redmine_statuses:
                rid, rname = rs["id"], rs["name"]
                rclosed = rs.get("is_closed", False)
                redmine_ids.add(rid)

                if rid in db_statuses:
                    row = db_statuses[rid]
                    if row.name != rname or row.is_closed != rclosed:
                        row.name = rname
                        row.is_closed = rclosed
                        results["statuses"]["updated"] += 1
                else:
                    session.add(
                        RedmineStatus(
                            redmine_status_id=rid, name=rname, is_closed=rclosed, is_active=True
                        )
                    )
                    results["statuses"]["added"] += 1

            for rid, row in list(db_statuses.items()):
                if rid not in redmine_ids:
                    row.is_active = False
                    results["statuses"]["hidden"] += 1
        except Exception as e:
            logger.error("Sync statuses failed: %s", e)

        # ── 2. Sync Versions ─────────────────────────────────────────
        try:
            # Получаем ID проекта из первой задачи
            proj_id = None
            resp_issues = await client.get(
                f"{base_url}/issues.json", headers=headers, params={"limit": 1}
            )
            resp_issues.raise_for_status()
            issues = resp_issues.json().get("issues", [])
            if issues:
                proj_id = issues[0].get("project", {}).get("id")

            if proj_id:
                resp_versions = await client.get(
                    f"{base_url}/projects/{proj_id}/versions.json", headers=headers
                )
                resp_versions.raise_for_status()
                redmine_versions = resp_versions.json().get("versions", [])

                result = await session.execute(
                    select(RedmineVersion).where(RedmineVersion.is_active)
                )
                db_versions = {v.redmine_version_id: v for v in result.scalars().all()}

                redmine_ids = set()
                for rv in redmine_versions:
                    vid, vname = rv["id"], rv["name"]
                    redmine_ids.add(vid)

                    if vid in db_versions:
                        row = db_versions[vid]
                        if row.name != vname:
                            row.name = vname
                            results["versions"]["updated"] += 1
                    else:
                        session.add(
                            RedmineVersion(redmine_version_id=vid, name=vname, is_active=True)
                        )
                        results["versions"]["added"] += 1

                for vid, row in list(db_versions.items()):
                    if vid not in redmine_ids:
                        row.is_active = False
                        results["versions"]["hidden"] += 1
        except Exception as e:
            logger.error("Sync versions failed: %s", e)

        # ── 3. Sync Priorities ───────────────────────────────────────
        try:
            resp = await client.get(
                f"{base_url}/enumerations/issue_priorities.json", headers=headers
            )
            resp.raise_for_status()
            redmine_priorities = resp.json().get("issue_priorities", [])

            result = await session.execute(select(RedminePriority).where(RedminePriority.is_active))
            db_priorities = {p.redmine_priority_id: p for p in result.scalars().all()}

            redmine_ids = set()
            for rp in redmine_priorities:
                pid, pname = rp["id"], rp["name"]
                redmine_ids.add(pid)

                if pid in db_priorities:
                    row = db_priorities[pid]
                    if row.name != pname:
                        row.name = pname
                        results["priorities"]["updated"] += 1
                else:
                    session.add(
                        RedminePriority(redmine_priority_id=pid, name=pname, is_active=True)
                    )
                    results["priorities"]["added"] += 1

            for pid, row in list(db_priorities.items()):
                if pid not in redmine_ids:
                    row.is_active = False
                    results["priorities"]["hidden"] += 1
        except Exception as e:
            logger.error("Sync priorities failed: %s", e)

    await session.commit()

    return JSONResponse({"ok": True, **results})
