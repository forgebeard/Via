"""Преобразование DATABASE_URL для async-движка."""

from database.session import async_database_url, sync_database_url_for_alembic


def test_async_database_url():
    u = async_database_url("postgresql://bot:secret@postgres:5432/redmine_matrix")
    assert u.startswith("postgresql+asyncpg://")


def test_sync_for_alembic():
    u = sync_database_url_for_alembic("postgresql://bot:x@localhost/db")
    assert "psycopg" in u
