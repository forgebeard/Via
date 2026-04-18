"""Тесты для хелперов из src/admin/main.py."""

from __future__ import annotations

import admin.main as main
import admin.routes.redmine as redmine_mod

# ═══════════════════════════════════════════════════════════════════════════
# _status_preset
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifyPreset:
    """_status_preset: определение пресета уведомлений."""

    def test_none_returns_all(self):
        assert main._status_preset(None) == "default"

    def test_empty_returns_all(self):
        assert main._status_preset([]) == "default"

    def test_all_returns_all(self):
        assert main._status_preset(["all"]) == "default"

    def test_all_with_others_returns_all(self):
        assert main._status_preset(["all", "new"]) == "default"

    def test_custom_returns_custom(self):
        assert main._status_preset(["new", "status_change"]) == "custom"

    def test_single_custom(self):
        assert main._status_preset(["overdue"]) == "custom"

    def test_matches_catalog_defaults_is_default(self):
        assert main._status_preset(["a", "b"], ["a", "b"]) == "default"
        assert main._status_preset(["b", "a"], ["a", "b"]) == "default"

    def test_subset_of_defaults_is_custom(self):
        assert main._status_preset(["a"], ["a", "b"]) == "custom"


# ═══════════════════════════════════════════════════════════════════════════
# _dimension_preset
# ═══════════════════════════════════════════════════════════════════════════


class TestDimensionPreset:
    def test_empty_and_all(self):
        assert main._dimension_preset(None, ["1"]) == "default"
        assert main._dimension_preset([], ["1"]) == "default"
        assert main._dimension_preset(["all"], ["1"]) == "default"

    def test_matches_defaults(self):
        assert main._dimension_preset(["x", "y"], ["x", "y"]) == "default"
        assert main._dimension_preset(["y", "x"], ["x", "y"]) == "default"

    def test_custom(self):
        assert main._dimension_preset(["x"], ["x", "y"]) == "custom"


# ═══════════════════════════════════════════════════════════════════════════
# _parse_work_hours_range
# ═══════════════════════════════════════════════════════════════════════════


class TestParseWorkHoursRange:
    """_parse_work_hours_range: парсинг диапазона рабочих часов."""

    def test_valid_range(self):
        assert main._parse_work_hours_range("09:00-18:00") == ("09:00", "18:00")

    def test_empty_string(self):
        assert main._parse_work_hours_range("") == ("", "")

    def test_none_value(self):
        assert main._parse_work_hours_range(None) == ("", "")  # type: ignore

    def test_no_dash_returns_empty(self):
        assert main._parse_work_hours_range("09:00") == ("", "")


# ═══════════════════════════════════════════════════════════════════════════
# _parse_work_days
# ═══════════════════════════════════════════════════════════════════════════


class TestParseWorkDays:
    """_parse_work_days: парсинг JSON списка рабочих дней."""

    def test_valid_json(self):
        assert main._parse_work_days("[0, 1, 2, 3, 4]") == [0, 1, 2, 3, 4]

    def test_empty_string(self):
        assert main._parse_work_days("") is None

    def test_none_value(self):
        assert main._parse_work_days(None) is None

    def test_invalid_json(self):
        assert main._parse_work_days("not json") is None

    def test_non_list_returns_none(self):
        assert main._parse_work_days('{"a": 1}') is None


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_notify
# ═══════════════════════════════════════════════════════════════════════════


class TestNormalizeNotify:
    """_normalize_notify: нормализация списка уведомлений."""

    def test_valid_values(self):
        allowed = ["all", "new", "status_change", "overdue", "reminder"]
        result = main._normalize_notify(["new", "overdue"], allowed)
        assert result == ["new", "overdue"]

    def test_filters_invalid(self):
        allowed = ["new", "status_change"]
        result = main._normalize_notify(["new", "invalid", "status_change"], allowed)
        assert result == ["new", "status_change"]

    def test_all_in_values_returns_all(self):
        allowed = ["new", "status_change"]
        result = main._normalize_notify(["all", "new"], allowed)
        assert result == ["all"]  # "all" → returns ["all"]

    def test_empty_returns_all(self):
        result = main._normalize_notify([])
        assert result == ["all"]

    def test_none_returns_all(self):
        result = main._normalize_notify(None)
        assert result == ["all"]

    def test_all_none_allowed_returns_all(self):
        result = main._normalize_notify(["invalid1", "invalid2"])
        assert result == ["all"]


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_versions
# ═══════════════════════════════════════════════════════════════════════════


class TestNormalizeVersions:
    """_normalize_versions: нормализация списка версий."""

    def test_valid_values(self):
        allowed = ["1.0", "2.0", "3.0"]
        result = main._normalize_versions(["1.0", "2.0"], allowed)
        assert result == ["1.0", "2.0"]

    def test_filters_invalid(self):
        allowed = ["1.0", "2.0"]
        result = main._normalize_versions(["1.0", "invalid"], allowed)
        assert result == ["1.0"]

    def test_empty_allowed_returns_empty(self):
        assert main._normalize_versions(["1.0"], []) == []

    def test_none_values_returns_empty(self):
        assert main._normalize_versions(None) == []

    def test_empty_values_returns_empty(self):
        assert main._normalize_versions([]) == []

    def test_deduplicates(self):
        allowed = ["1.0", "2.0"]
        result = main._normalize_versions(["1.0", "1.0", "2.0"], allowed)
        assert result == ["1.0", "2.0"]

    def test_strips_whitespace(self):
        allowed = ["1.0", "2.0"]
        result = main._normalize_versions([" 1.0 ", " 2.0 "], allowed)
        assert result == ["1.0", "2.0"]

    def test_skips_empty_strings(self):
        allowed = ["1.0", "2.0"]
        result = main._normalize_versions(["", "  ", "1.0"], allowed)
        assert result == ["1.0"]


# ═══════════════════════════════════════════════════════════════════════════
# _RedmineSearchBreaker (из admin.routes.redmine)
# ═══════════════════════════════════════════════════════════════════════════


class TestRedmineSearchBreaker:
    """_RedmineSearchBreaker: circuit breaker для поиска в Redmine."""

    def test_initially_not_blocked(self):
        breaker = redmine_mod._RedmineSearchBreaker()
        assert breaker.blocked() is False

    def test_success_resets(self):
        breaker = redmine_mod._RedmineSearchBreaker()
        for _ in range(10):
            breaker.on_failure()
        breaker.on_success()
        assert breaker.blocked() is False

    def test_five_failures_blocks(self):
        breaker = redmine_mod._RedmineSearchBreaker()
        for _ in range(5):
            breaker.on_failure()
        assert breaker.blocked() is True

    def test_four_failures_does_not_block(self):
        breaker = redmine_mod._RedmineSearchBreaker()
        for _ in range(4):
            breaker.on_failure()
        assert breaker.blocked() is False

    def test_cooldown_duration_60s(self):
        import time

        breaker = redmine_mod._RedmineSearchBreaker()
        now = time.time()
        for _ in range(5):
            breaker.on_failure()
        assert breaker.cooldown_until_ts > now + 55
        assert breaker.cooldown_until_ts < now + 65

    def test_failures_counter_resets_on_success(self):
        breaker = redmine_mod._RedmineSearchBreaker()
        for _ in range(3):
            breaker.on_failure()
        breaker.on_success()
        assert breaker.failures == 0
