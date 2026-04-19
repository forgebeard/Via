"""
Единая отправка m.room.message в Matrix: повторы и экспоненциальный backoff.

Используется и корневым bot.py (свой AsyncClient), и matrix_client (singleton).

Ответ успешной отправки в nio обычно содержит event_id; ошибки — RoomSendError
или ответ с status_code без event_id. В тестах nio подменяют, поэтому проверка
не только через isinstance(RoomSendError).
"""

import asyncio
import logging

from nio import RoomSendError

logger = logging.getLogger("redmine_bot")


def _log_matrix_send_response(resp, room_id: str, *, prefix: str = "Matrix room_send") -> None:
    """Детальный разбор ответа nio для диагностики M_FORBIDDEN и др."""
    parts = [f"{prefix} room={room_id!r}"]
    for key in ("message", "status_code", "body", "transport_response", "event_id"):
        val = getattr(resp, key, None)
        if val is not None:
            parts.append(f"{key}={val!r}")
    if isinstance(resp, RoomSendError):
        parts.append(f"type=RoomSendError")
    logger.warning("; ".join(parts))


def _get_retry_settings() -> tuple[int, float]:
    """Читает retry-настройки из config (с fallback)."""
    try:
        from config import MATRIX_RETRY_BASE_DELAY_SEC, MATRIX_RETRY_MAX_ATTEMPTS

        return MATRIX_RETRY_MAX_ATTEMPTS, MATRIX_RETRY_BASE_DELAY_SEC
    except Exception:
        return 3, 1.0


# Re-export для обратной совместимости (тесты)
MAX_RETRIES, RETRY_BASE_SEC = _get_retry_settings()


async def room_send_with_retry(client, room_id, content):
    """
    Отправка в комнату с повторными попытками.

    При RoomSendError или исключении сети — warning и пауза до MAX_RETRIES раз.
    Итог: проброс последней ошибки.
    """
    max_retries, retry_base_sec = _get_retry_settings()
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.room_send(
                room_id=room_id, message_type="m.room.message", content=content
            )
            # Успех: у ответа nio есть event_id (совместимо с моками, где isinstance(RoomSendError) ломается)
            if getattr(resp, "event_id", None):
                return resp
            if isinstance(resp, RoomSendError):
                _log_matrix_send_response(resp, room_id)
                last_err = RuntimeError(
                    f"Matrix room_send error: {getattr(resp, 'message', resp)} "
                    f"(status_code={getattr(resp, 'status_code', None)}, room={room_id})"
                )
            elif getattr(resp, "status_code", None) is not None and not getattr(
                resp, "event_id", None
            ):
                _log_matrix_send_response(resp, room_id)
                last_err = RuntimeError(
                    f"Matrix room_send error: {getattr(resp, 'message', resp)} "
                    f"(status_code={resp.status_code}, room={room_id})"
                )
            else:
                return resp
        except Exception as e:
            last_err = e
            logger.warning(
                "Matrix send exception (%s/%s) room=%s: %s: %s",
                attempt,
                max_retries,
                room_id,
                type(e).__name__,
                e,
            )

        if attempt >= max_retries:
            break

        delay = retry_base_sec * (2 ** (attempt - 1))
        logger.warning(
            "Matrix send failed (%s/%s): %s; retry in %.1fs",
            attempt,
            max_retries,
            last_err,
            delay,
        )
        await asyncio.sleep(delay)

    if last_err is not None:
        raise last_err
    raise RuntimeError(f"Matrix room_send failed after {max_retries} attempts (room={room_id})")
