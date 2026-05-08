"""Notificaciones por Telegram cuando un cliente escribe en el chat en vivo.

Reusa el helper genérico ``orders.telegram.notify_admin`` para no duplicar la
configuración del bot. Aplica un debounce simple por sala (120s) usando el
cache de Django para no spamear al admin si el cliente manda 5 mensajes
seguidos.
"""

from __future__ import annotations

import html
import logging

from django.core.cache import cache

from .models import ChatMessage, ChatRoom

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 120
_CACHE_KEY = "livechat:tg_notified:{room_id}"
_ADMIN_BASE = "https://ecormecejhelizstore.com/panel-jheliz-2026"


def _build_text(room: ChatRoom, message: ChatMessage) -> str:
    who = room.display_name or "Cliente"
    email = room.customer_email or "(sin correo)"
    body = (message.body or "").strip()
    if len(body) > 400:
        body = body[:397] + "…"
    return (
        f"<b>💬 Chat nuevo de {html.escape(who)}</b>\n"
        f"<i>{html.escape(email)}</i>\n\n"
        f"{html.escape(body)}"
    )


def _build_buttons(room: ChatRoom) -> list[list[dict]]:
    return [[
        {
            "text": "Abrir chat",
            "url": f"{_ADMIN_BASE}/livechat/{room.pk}/",
        },
    ]]


def notify_admin_new_customer_message(
    room: ChatRoom, message: ChatMessage,
) -> None:
    """Manda un msg a Telegram al admin con el texto del cliente.

    Aplica debounce por sala: si ya notificamos por esta sala en los últimos
    ``_DEBOUNCE_SECONDS`` no volvemos a mandar. Esto evita spam cuando el
    cliente manda muchos mensajes en ráfaga.

    Cualquier excepción se loguea pero no propaga: nunca debe romper el
    `send` del cliente si Telegram está caído.
    """
    if message.sender != ChatMessage.Sender.CUSTOMER:
        return
    cache_key = _CACHE_KEY.format(room_id=room.pk)
    if cache.get(cache_key):
        return
    try:
        # Import diferido para no crear ciclos con orders.* en startup.
        from orders.telegram import is_configured, notify_admin
    except Exception:  # pragma: no cover
        logger.exception("No se pudo importar orders.telegram")
        return

    if not is_configured():
        return

    try:
        notify_admin(_build_text(room, message), buttons=_build_buttons(room))
        cache.set(cache_key, True, _DEBOUNCE_SECONDS)
    except Exception:  # pragma: no cover
        logger.exception(
            "No se pudo notificar al admin del chat sala=%s", room.pk,
        )
