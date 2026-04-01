import os
import re

import pytest
from fastapi.testclient import TestClient

import admin_main
os.environ.setdefault("APP_MASTER_KEY", "0123456789abcdef0123456789abcdef")


def _db_ready() -> bool:
    db_url = os.getenv("DATABASE_URL", "")
    return bool(db_url) and db_url.startswith("postgresql://")


@pytest.fixture
def client():
    return TestClient(admin_main.app)


def test_matrix_bind_redirects_to_login_without_auth(client: TestClient):
    r = client.get("/matrix/bind", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    loc = r.headers.get("location", "")
    assert loc.endswith("/login") or loc.endswith("/setup"), loc


@pytest.mark.skipif(not _db_ready(), reason="DB auth требует DATABASE_URL (postgresql://...)")
def test_matrix_bind_flow_dev_echo_updates_bot_user_room(client: TestClient):
    os.environ["MATRIX_CODE_DEV_ECHO"] = "1"

    # Тот же админ, что и в test_admin_main (одна БД в CI).
    email = "test_admin@example.com"
    redmine_id = 123
    room_id = "!room123:example.com"

    client.get("/setup", follow_redirects=True)
    csrf = client.cookies.get("admin_csrf")
    client.post(
        "/setup",
        data={"email": email, "password": "StrongPassword123", "csrf_token": csrf},
        follow_redirects=False,
    )
    client.get("/login")
    csrf_login = client.cookies.get("admin_csrf")
    client.post(
        "/login",
        data={"email": email, "password": "StrongPassword123", "csrf_token": csrf_login},
        follow_redirects=True,
    )

    client.get("/matrix/bind", follow_redirects=True)
    csrf_bind = client.cookies.get("admin_csrf")
    start = client.post(
        "/matrix/bind/start",
        data={
            "redmine_id": str(redmine_id),
            "room_id": room_id,
            "csrf_token": csrf_bind or "",
        },
        follow_redirects=True,
    )
    assert start.status_code == 200
    m = re.search(r"Dev code:</strong>\s*<code>(\d{6})</code>", start.text)
    assert m, f"Не найден Dev code в ответе: {start.text[:300]}"
    code = m.group(1)

    csrf_confirm = client.cookies.get("admin_csrf")
    confirm = client.post(
        "/matrix/bind/confirm",
        data={
            "redmine_id": str(redmine_id),
            "room_id": room_id,
            "code": code,
            "csrf_token": csrf_confirm or "",
        },
        follow_redirects=False,
    )
    assert confirm.status_code in (303, 302)

    # Проверяем, что bot_users.room обновился.
    import asyncio

    from database.models import BotUser
    from database.session import get_session_factory
    from sqlalchemy import select

    async def _check():
        factory = get_session_factory()
        async with factory() as session:
            res = await session.execute(select(BotUser).where(BotUser.redmine_id == redmine_id))
            return res.scalar_one_or_none()

    user_row = asyncio.run(_check())
    assert user_row is not None
    assert user_row.room == room_id

