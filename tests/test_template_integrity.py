"""Проверка целостности HTML-шаблонов.

Ловит ошибки которые unit-тесты пропускают:
- missing id в HTML (но JS ищет getElementById)
- button без type="button" внутри form (срабатывает submit)
- missing name у input (FormData не собирает)
- JS ссылается на несуществующий ID
"""

from __future__ import annotations

import re
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "admin"
_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "admin" / "js"


def _read_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _read_js(name: str) -> str:
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


def _find_ids(html: str) -> set[str]:
    """Находит все id="..." в HTML."""
    return set(re.findall(r'id="([^"]+)"', html))


def _find_names(html: str) -> set[str]:
    """Находит все name="..." в HTML."""
    return set(re.findall(r'name="([^"]+)"', html))


def _find_js_id_refs(js: str) -> set[str]:
    """Находит getElementById("...") в JS."""
    return set(re.findall(r'getElementById\("([^"]+)"\)', js))


def _find_button_types(html: str) -> list[dict]:
    """Находит все <button> и их type."""
    results = []
    for m in re.finditer(r"<button\b([^>]*)>", html):
        attrs = m.group(1)
        type_m = re.search(r'type="([^"]*)"', attrs)
        id_m = re.search(r'id="([^"]*)"', attrs)
        text_m = re.search(r">([^<]+)</button", html[m.start() :])
        results.append(
            {
                "type": type_m.group(1) if type_m else "(no type)",
                "id": id_m.group(1) if id_m else "(no id)",
                "text": (text_m.group(1).strip() if text_m else "?")[:30],
            }
        )
    return results


# ── Tests ───────────────────────────────────────────────────────────────────


class TestOnboardingTemplate:
    """onboarding.html — критически важная страница настройки."""

    def setup_method(self):
        self.html = _read_template("panel/onboarding.html")
        self.js = _read_js("onboarding.js")
        self.ids = _find_ids(self.html)
        self.js_ids = _find_js_id_refs(self.js)

    def test_check_access_button_has_correct_id(self):
        """Кнопка «Проверить доступ» должна иметь id="check-access-btn"."""
        # Находим кнопку по тексту
        btn_match = re.search(r"<button[^>]*>Проверить доступ</button>", self.html)
        assert btn_match, "Кнопка «Проверить доступ» не найдена в шаблоне"
        attrs = btn_match.group(0)
        assert 'id="check-access-btn"' in attrs, (
            f'Кнопка «Проверить доступ» не имеет id="check-access-btn". Атрибуты: {attrs}'
        )

    def test_check_access_button_is_type_button(self):
        """Кнопка «Проверить доступ» должна быть type=\"button\" (не submit)."""
        btn_match = re.search(r"<button[^>]*>Проверить доступ</button>", self.html)
        assert btn_match, "Кнопка «Проверить доступ» не найдена"
        attrs = btn_match.group(0)
        assert 'type="button"' in attrs, (
            f'Кнопка «Проверить доступ» не имеет type="button". Атрибуты: {attrs}'
        )

    def test_save_button_is_type_submit(self):
        """Кнопка «Сохранить» должна быть type=\"submit\"."""
        btn_match = re.search(r"<button[^>]*>Сохранить</button>", self.html)
        assert btn_match, "Кнопка «Сохранить» не найдена"
        attrs = btn_match.group(0)
        assert 'type="submit"' in attrs, (
            f'Кнопка «Сохранить» не имеет type="submit". Атрибуты: {attrs}'
        )

    def test_js_references_exist_in_html(self):
        """Все getElementById в onboarding.js должны существовать в HTML."""
        missing = self.js_ids - self.ids
        assert not missing, (
            f"JS ссылается на ID которых нет в HTML: {missing}. Доступные ID: {sorted(self.ids)}"
        )

    def test_secret_fields_have_name_attributes(self):
        """Все поля секретов должны иметь name=\"secret_...\"."""
        expected_names = {
            "secret_REDMINE_URL",
            "secret_REDMINE_API_KEY",
            "secret_MATRIX_HOMESERVER",
            "secret_MATRIX_USER_ID",
            "secret_MATRIX_ACCESS_TOKEN",
        }
        html_names = _find_names(self.html)
        missing = expected_names - html_names
        assert not missing, f"Поля секретов без name атрибута: {missing}"

    def test_csrf_token_in_form(self):
        """Форма должна содержать csrf_token hidden поле."""
        assert 'name="csrf_token"' in self.html, "CSRF токен не найден в форме"


class TestAllTemplatesHaveCsrf:
    """Все формы POST должны иметь CSRF токен."""

    def _check_template(self, path: str):
        html = _read_template(path)
        has_form_post = re.search(r'<form[^>]*method="post"', html, re.IGNORECASE)
        has_csrf = 'name="csrf_token"' in html
        if has_form_post:
            assert has_csrf, f"Форма в {path} не содержит csrf_token"

    def test_onboarding_has_csrf(self):
        self._check_template("panel/onboarding.html")

    def test_login_has_csrf(self):
        self._check_template("auth/login.html")

    def test_setup_has_csrf(self):
        self._check_template("auth/setup.html")


class TestNoDanglingButtonWithoutType:
    """Кнопки внутри форм без type=button должны быть type=submit."""

    def test_onboarding_buttons_have_explicit_type(self):
        """Все кнопки на onboarding должны иметь явный type."""
        buttons = _find_button_types(_read_template("panel/onboarding.html"))
        for btn in buttons:
            assert btn["type"] in ("button", "submit"), (
                f"Кнопка «{btn['text']}» (id={btn['id']}) не имеет явного type. "
                f"Браузер по умолчанию считает это submit."
            )
