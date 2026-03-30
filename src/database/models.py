"""ORM-модели конфигурации бота (пользователи, маршруты в Matrix)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BotUser(Base):
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    redmine_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    room: Mapped[str] = mapped_column(Text, nullable=False)
    notify: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["all"])
    work_hours: Mapped[str | None] = mapped_column(String(32), nullable=True)
    work_days: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    dnd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StatusRoomRoute(Base):
    __tablename__ = "status_room_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(Text, nullable=False)


class VersionRoomRoute(Base):
    __tablename__ = "version_room_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(Text, nullable=False)
