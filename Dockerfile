# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# Многоступенчатая сборка образа бота Redmine → Matrix.
#
# Зачем два этапа:
#   - builder: ставим зависимости в изолированный venv — финальный слой не тянет
#     pip, кэш загрузок и лишние инструменты сборки.
#   - runtime: только интерпретатор, venv с пакетами и код приложения — меньше
#     поверхность атаки и размер образа.
#
# Python 3.11 — совпадает с целевой версией проекта (см. README, CI).
# -----------------------------------------------------------------------------

# ============ Этап 1: установка зависимостей ==================================
FROM python:3.11-slim-bookworm AS builder

# Не буферизовать stdout/stderr — логи сразу видны в `docker logs`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# venv в фиксированном пути — копируем целиком в финальный образ.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Сначала только requirements — слой кэшируется, пока не изменится список пакетов.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============ Этап 2: минимальный runtime =====================================
FROM python:3.11-slim-bookworm AS runtime

# PYTHONPATH=/app/src — импорты `from bot` / `from config` как в коде (аналог CI: PYTHONPATH=src).
# WORKDIR=/app — пакет `src` находится как import src.* (точка входа CMD, healthcheck compose, CI docker job).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Непривилегированный пользователь: процесс в контейнере не root (best practice).
RUN groupadd --system --gid 1000 bot && \
    useradd --system --uid 1000 --gid bot --home /app --shell /sbin/nologin bot

WORKDIR /app

# Переносим только установленные пакеты из builder (без исходников pip).
COPY --from=builder /opt/venv /opt/venv

# Код приложения: пакет src/ (импорты matrix_send, utils и т.д., а также модули bot и admin).
COPY --chown=bot:bot src/ ./src/
COPY --chown=bot:bot templates/ ./templates/
COPY --chown=bot:bot static/ ./static/
COPY --chown=bot:bot scripts/ ./scripts/
COPY --chown=bot:bot alembic.ini .
COPY --chown=bot:bot alembic/ ./alembic/

# /app должен принадлежать bot: иначе не создать data/bot.log на томе при первом запуске
# и нет прав на запись в каталог приложения.
RUN chown -R bot:bot /app

# data/ создаётся на томе при монтировании; при несовпадении uid с хостом см. README (chown).

USER bot

# -m = run as module (src/bot/main.py), -u = unbuffered.
CMD ["python", "-u", "-m", "src.bot.main"]
