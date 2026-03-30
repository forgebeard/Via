import os

from fastapi.testclient import TestClient

import pytest


# Должно быть выставлено до импортов/создания TestClient,
# чтобы middleware по ADMIN_TOKEN работал предсказуемо.
os.environ.setdefault("ADMIN_TOKEN", "test_admin_token")

# На тесты страниц, где не используется БД (login/health/search без Redmine),
# DATABASE_URL не требуется.

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
    assert "Админка бота" in r.text


def test_login_post_wrong_token_returns_401(client: TestClient):
    r = client.post("/login", data={"token": "wrong"})
    assert r.status_code == 401


def test_users_redirects_to_login_without_auth(client: TestClient):
    r = client.get("/users", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert r.headers.get("location", "").endswith("/login")


def test_redmine_search_without_redmine_creds_returns_empty(client: TestClient):
    r = client.get(
        "/redmine/users/search?q=ivan",
        headers={"X-Admin-Token": os.environ["ADMIN_TOKEN"]},
    )
    assert r.status_code == 200
    assert r.text == ""

