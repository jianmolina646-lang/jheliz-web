"""Registro seguro de identificadores devueltos por Telegram."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def record_sent_message(bot_key: str, payload: dict, response: dict) -> None:
    """Guarda solo IDs y metadatos; nunca texto, token ni credenciales."""
    if not response.get("ok"):
        return
    result = response.get("result") or {}
    message_id = result.get("message_id")
    chat = result.get("chat") or {}
    chat_id = chat.get("id", payload.get("chat_id"))
    if message_id is None or chat_id in (None, ""):
        return
    try:
        from .models import TelegramSentMessage

        TelegramSentMessage.objects.get_or_create(
            bot_key=bot_key[:32],
            chat_id=str(chat_id)[:64],
            message_id=int(message_id),
        )
    except Exception:
        logger.exception("No se pudo registrar el ID del mensaje Telegram")
