import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from alembic import context
from database.models import Base  # noqa: E402
from database.session import sync_database_url_for_alembic  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """URL для миграций: приоритет ``DATABASE_URL``, иначе ``sqlalchemy.url`` из alembic.ini."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raw = (config.get_main_option("sqlalchemy.url") or "").strip()
    if not raw or raw.startswith("driver://"):
        raise RuntimeError(
            "Не задан рабочий URL Postgres для Alembic.\n"
            "  export DATABASE_URL=postgresql://USER:PASS@127.0.0.1:5432/DBNAME\n"
            "Затем из корня проекта: alembic upgrade head\n"
            "\n"
            "(Значение driver:// в alembic.ini — только заглушка и не является драйвером БД.)"
        )
    if not raw.startswith(("postgresql://", "postgresql+")):
        raise RuntimeError(
            "DATABASE_URL / sqlalchemy.url должен начинаться с postgresql:// "
            f"или postgresql+… (сейчас: {raw[:80]!r}…)"
        )
    return sync_database_url_for_alembic(raw)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
