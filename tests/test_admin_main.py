import os

from fastapi.testclient import TestClient

import pytest


# Для password auth и encrypted-secrets на старте нужен master key.
os.environ.setdefault("APP_MASTER_KEY", "0123456789abcdef0123456789abcdef")

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
    assert "Пароль" in r.text


def test_setup_creates_first_admin(client: TestClient):
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or not db_url.startswith("postgresql://"):
        pytest.skip("Тест требует Postgres (DATABASE_URL)")
    page = client.get("/setup")
    assert page.status_code == 200
    token = page.cookies.get("admin_csrf")
    r = client.post(
        "/setup",
        data={
            "email": "first_admin@example.com",
            "password": "StrongPassword123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_users_redirects_to_login_without_auth(client: TestClient):
    r = client.get("/users", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert r.headers.get("location", "").endswith("/login")


def test_redmine_search_without_redmine_creds_returns_empty(client: TestClient):
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or not db_url.startswith("postgresql://"):
        pytest.skip("Тест требует Postgres (DATABASE_URL)")

    setup = client.get("/setup")
    token = setup.cookies.get("admin_csrf")
    client.post(
        "/setup",
        data={
            "email": "test_admin@example.com",
            "password": "StrongPassword123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    login = client.get("/login")
    ltoken = login.cookies.get("admin_csrf")
    client.post(
        "/login",
        data={"email": "test_admin@example.com", "password": "StrongPassword123", "csrf_token": ltoken},
        follow_redirects=True,
    )
    r = client.get("/redmine/users/search?q=ivan")
    assert r.status_code == 200
    assert r.text == ""

