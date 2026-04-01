"""
Веб-админка: пользователи бота и маршруты Matrix (Postgres).

Запуск: uvicorn admin_main:app --host 0.0.0.0 --port 8080
Требуется DATABASE_URL (доступ к UI — через email/password).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from database.load_config import row_counts
from database.session import get_session
from ops.docker_control import DockerControlError, get_service_status

from admin.csp import admin_csp_value as _admin_csp_value, security_headers_middleware
from admin.lifespan import admin_lifespan as _admin_lifespan
from admin.middleware.auth import AuthMiddleware
from admin.routers.app_users import router as app_users_router
from admin.routers.auth import router as auth_router
from admin.routers.groups import router as groups_router
from admin.routers.health import router as health_router
from admin.routers.matrix_bind import router as matrix_bind_router
from admin.routers.me import router as me_router
from admin.routers.ops import router as ops_router
from admin.routers.redmine import router as redmine_router
from admin.routers.routes_cfg import router as routes_cfg_router
from admin.routers.secrets import router as secrets_router
from admin.routers.users import router as users_router
from admin.runtime import process_started_at
from admin.session_logic import runtime_status_from_file
from admin.templates_env import admin_asset_version as _admin_asset_version, templates

app = FastAPI(
    title="Matrix bot control panel",
    version="0.1.0",
    lifespan=_admin_lifespan,
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(ops_router)
app.include_router(secrets_router)
app.include_router(app_users_router)
app.include_router(groups_router)
app.include_router(users_router)
app.include_router(redmine_router)
app.include_router(routes_cfg_router)
app.include_router(matrix_bind_router)
app.include_router(me_router)
app.middleware("http")(security_headers_middleware)

_STATIC_ROOT = _ROOT / "static"
if _STATIC_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_ROOT)), name="static")

app.add_middleware(AuthMiddleware)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = getattr(request.state, "current_user", None)
    if not user or getattr(user, "role", "") != "admin":
        raise HTTPException(403, "Только admin")
    nu, ns, nv = await row_counts(session)
    runtime_file = runtime_status_from_file()
    try:
        runtime_docker = get_service_status()
    except DockerControlError as e:
        runtime_docker = {"state": "error", "detail": str(e), "service": os.getenv("DOCKER_TARGET_SERVICE", "bot")}
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "users_count": nu,
            "status_routes_count": ns,
            "version_routes_count": nv,
            "runtime_status": {
                "uptime_s": int(time.monotonic() - process_started_at),
                "live": True,
                "ready": True,
                "cycle": runtime_file,
                "docker": runtime_docker,
            },
        },
    )
