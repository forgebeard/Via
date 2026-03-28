"""
Matrix-клиент: подключение, отправка сообщений.

Обёртка над nio.AsyncClient с retry-логикой и форматированием HTML.
Использует access_token (без пароля).
"""

import asyncio
import logging
import re

from nio import AsyncClient, RoomSendError

from config import (
    MATRIX_HOMESERVER,
    MATRIX_ACCESS_TOKEN,
    MATRIX_USER_ID,
    MATRIX_DEVICE_ID,
)

logger = logging.getLogger("redmine_bot")

# ═══════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ═══════════════════════════════════════════════════════════════

MAX_RETRIES = 3
RETRY_DELAY = 2  # секунды


# ═══════════════════════════════════════════════════════════════
# КЛИЕНТ
# ═══════════════════════════════════════════════════════════════

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    """
    Возвращает подключённый Matrix-клиент (singleton).
    Использует access_token — логин не нужен.
    """
    global _client

    if _client is not None:
        return _client

    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    client.access_token = MATRIX_ACCESS_TOKEN
    client.device_id = MATRIX_DEVICE_ID or "BOT"
    client.user_id = MATRIX_USER_ID

    logger.info(f"✅ Matrix: клиент создан для {MATRIX_USER_ID}")
    _client = client
    return _client


async def close_client():
    """Закрывает Matrix-клиент."""
    global _client
    if _client:
        await _client.close()
        _client = None
        logger.info("Matrix: клиент закрыт")


async def send_message(room_id: str, html: str, text: str = "") -> bool:
    """
    Отправляет HTML-сообщение в комнату Matrix.

    Args:
        room_id: ID комнаты (!xxx:server)
        html: HTML-тело сообщения
        text: Plaintext fallback (если пусто — strip HTML)

    Returns:
        True при успехе, False при ошибке.
    """
    if not text:
        text = re.sub(r"<[^>]+>", "", html)

    client = await get_client()

    content = {
        "msgtype": "m.text",
        "body": text,
        "format": "org.matrix.custom.html",
        "formatted_body": html,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )
            if isinstance(resp, RoomSendError):
                logger.error(f"❌ Matrix send error (attempt {attempt}): {resp}")
            else:
                return True
        except Exception as e:
            logger.error(f"❌ Matrix exception (attempt {attempt}): {e}")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ Не удалось отправить в {room_id} после {MAX_RETRIES} попыток")
    return False