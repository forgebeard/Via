import os

from fastapi.testclient import TestClient

import pytest


# Для auth по magic-link требуется Postgres (DATABASE_URL).
# Эндпоинты без cookie редиректят на /login без попыток подключаться к БД.

os.environ.setdefault("ADMIN_BOOTSTRAP_FIRST_ADMIN", "1")

import admin_main  # noqa: E402


@pytest.fixture
def client():
    return TestClient(admin_main.app)


def test_health_ok(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_page_ok(client: TestClient):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Панель управления" in r.text
    assert "Email" in r.text


def test_users_redirects_to_login_without_auth(client: TestClient):
    r = client.get("/users", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert r.headers.get("location", "").endswith("/login")


def test_redmine_search_without_redmine_creds_returns_empty(client: TestClient):
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or not db_url.startswith("postgresql://"):
        pytest.skip("Тест требует Postgres (DATABASE_URL) для magic-link auth")

    # В MVP без SMTP редиректит сразу на /magic и выставляет cookie.
    client.post(
        "/login",
        data={"email": "test_admin@example.com"},
        follow_redirects=True,
    )
    r = client.get("/redmine/users/search?q=ivan")
    assert r.status_code == 200
    assert r.text == ""

