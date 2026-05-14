# Ruff — остаточный долг

Исторические замечания вне текущих PR могут оставаться в дереве. Полный проход: `python -m ruff check src/` и `python -m ruff format --check src/` (из корня репо, см. [docs/index.md](index.md)).

При массовой зачистке: `ruff check src/ --fix`, затем `ruff format src/`. Hot-path файлы (`bot/main.py`, `journal_handlers.py`, `sender.py`, `matrix_send.py`) — предпочитать узкий `except` или логирование вместо немого `continue` (категория `S112` и аналоги).
