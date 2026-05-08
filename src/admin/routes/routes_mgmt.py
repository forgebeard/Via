"""Legacy routes are disabled in rules-only release."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["routes_mgmt"])
_LEGACY_ROUTES_REMOVED = "Legacy routing endpoints removed in rules-only v1."


# ── Status routes (legacy GET only) ──────────────────────────────────────────


@router.get("/routes/status")
async def routes_status_legacy_redirect():
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


# ── Version routes (canonical under /settings) ───────────────────────────────


@router.get("/settings/routes/version")
async def settings_routes_version_get():
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


@router.post("/settings/routes/version")
async def settings_routes_version_post():
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


@router.post("/settings/routes/version/{row_id}/delete")
async def settings_routes_version_delete(
    row_id: int,
):
    del row_id
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


@router.get("/routes/version")
async def routes_version_legacy_redirect_to_canonical():
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


@router.post("/routes/version")
async def routes_version_post_legacy_gone():
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)


@router.post("/routes/version/{row_id}/delete")
async def routes_version_delete_legacy_gone(row_id: int):
    del row_id
    raise HTTPException(status_code=410, detail=_LEGACY_ROUTES_REMOVED)
