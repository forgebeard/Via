from datetime import timedelta

from bot.utils_text import format_duration


def test_format_duration():
    assert "с" in format_duration(timedelta(seconds=30))
    assert "мин" in format_duration(timedelta(minutes=3, seconds=5))
    assert "ч" in format_duration(timedelta(hours=2, minutes=1))
