"""Thin-bot command worker: pull commands from admin backend and deliver to Matrix."""

from __future__ import annotations

import logging

import httpx

from matrix_send import room_send_with_retry

logger = logging.getLogger("redmine_bot")
_COMMANDS_TOKEN_WARNING_EMITTED = False


async def process_backend_commands(
    client,
    *,
    admin_url: str,
    api_token: str = "",
    limit: int = 20,
) -> int:
    """Pull delivery commands from backend, send them, and report ack/error."""
    base = (admin_url or "").rstrip("/")
    if not base:
        return 0
    token = (api_token or "").strip()
    if not token:
        global _COMMANDS_TOKEN_WARNING_EMITTED
        if not _COMMANDS_TOKEN_WARNING_EMITTED:
            logger.warning("commands_pull_disabled: BOT_INTERNAL_API_TOKEN не задан")
            _COMMANDS_TOKEN_WARNING_EMITTED = True
        return 0

    pull_url = f"{base}/api/bot/commands"
    timeout = httpx.Timeout(15.0, connect=5.0)
    processed = 0
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=timeout) as http:
        try:
            resp = await http.get(pull_url, params={"limit": limit}, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            logger.warning("commands_pull_failed: %s", exc)
            return 0

        commands = body.get("commands") if isinstance(body, dict) else None
        if not isinstance(commands, list) or not commands:
            return 0

        for cmd in commands:
            if not isinstance(cmd, dict):
                continue
            command_id = cmd.get("command_id")
            room_id = cmd.get("room_id")
            payload = cmd.get("payload")
            if not command_id or not room_id or not isinstance(payload, dict):
                continue

            ack_url = f"{base}/api/bot/commands/{command_id}/ack"
            err_url = f"{base}/api/bot/commands/{command_id}/error"
            try:
                await room_send_with_retry(client, room_id, payload)
                ack_resp = await http.post(ack_url, headers=headers)
                ack_resp.raise_for_status()
                processed += 1
            except Exception as exc:
                err = str(exc).strip() or "delivery_failed"
                try:
                    err_resp = await http.post(
                        err_url, params={"error": err[:4000]}, headers=headers
                    )
                    err_resp.raise_for_status()
                except Exception as report_exc:
                    logger.debug("commands_error_report_failed: %s", report_exc)

    return processed
