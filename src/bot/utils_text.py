"""Текстовые утилиты для шаблонов журнального движка."""

from __future__ import annotations

from datetime import timedelta


def format_duration(delta: timedelta) -> str:
    """Человекочитаемая длительность (RU), стабильная сигнатура для локализации позже."""
    total_sec = int(max(0, delta.total_seconds()))
    if total_sec < 60:
        return f"{total_sec} с"
    m, s = divmod(total_sec, 60)
    if m < 60:
        return f"{m} мин {s} с" if s else f"{m} мин"
    h, m2 = divmod(m, 60)
    if h < 48:
        return f"{h} ч {m2} мин" if m2 else f"{h} ч"
    d, h2 = divmod(h, 24)
    return f"{d} д {h2} ч" if h2 else f"{d} д"
