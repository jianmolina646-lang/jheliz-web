"""Bot central y resúmenes Telegram de Jheliz Control."""

from __future__ import annotations

import hashlib
import html
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Subscription, TelegramConnection

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


def _call(method, **payload):
    token = settings.JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN no configurado")
    response = requests.post(API.format(token=token, method=method), json=payload, timeout=35)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram rechazó la solicitud"))
    return data


def send_message(chat_id, text):
    return _call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


def subscriptions_for_owner(owner_id):
    """
    Alcance canónico para cualquier dato enviado por Telegram.

    Las tres relaciones deben pertenecer al mismo revendedor. Esto evita una
    fuga incluso si una importación o edición administrativa dejara una fila
    inconsistente (suscripción de A apuntando accidentalmente a cliente de B).
    """
    return Subscription.objects.filter(
        owner_id=owner_id,
        client__owner_id=owner_id,
        service__owner_id=owner_id,
        is_archived=False,
    )


@transaction.atomic
def link_chat(raw_token, chat):
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    connection = (
        TelegramConnection.objects.select_for_update()
        .filter(link_token_digest=digest, link_expires_at__gt=timezone.now())
        .first()
    )
    if not connection:
        return False
    TelegramConnection.objects.filter(chat_id=str(chat["id"])).exclude(pk=connection.pk).update(
        chat_id=None, is_enabled=False
    )
    connection.chat_id = str(chat["id"])
    connection.telegram_username = chat.get("username", "")
    connection.linked_at = timezone.now()
    connection.link_token_digest = ""
    connection.link_expires_at = None
    connection.is_enabled = True
    connection.save()
    return True


def process_update(update):
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    if not chat.get("id"):
        return
    if text.startswith("/start "):
        linked = link_chat(text.split(maxsplit=1)[1], chat)
        if linked:
            send_message(chat["id"], "✅ <b>Telegram vinculado</b>\nRecibirás únicamente las alertas de tus clientes.")
        else:
            send_message(chat["id"], "⚠️ Este enlace venció o ya fue utilizado. Genera otro desde Jheliz Control.")
    elif text == "/start":
        send_message(chat["id"], "Abre Jheliz Control y pulsa <b>Vincular Telegram</b>.")
    elif text == "/estado":
        linked = TelegramConnection.objects.filter(chat_id=str(chat["id"]), is_enabled=True).exists()
        send_message(chat["id"], "✅ Alertas activas." if linked else "Telegram no está vinculado.")


def run_polling():
    offset = 0
    while True:
        try:
            data = _call("getUpdates", offset=offset, timeout=25, allowed_updates=["message"])
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                process_update(update)
        except Exception:
            logger.exception("Polling de alertas Telegram falló")
            time.sleep(5)


def send_expiry_digests(today=None):
    today = today or timezone.localdate()
    sent = 0
    connections = (
        TelegramConnection.objects.filter(is_enabled=True)
        .exclude(chat_id=None)
        .select_related("owner")
    )
    for connection in connections:
        if connection.last_digest_date == today:
            continue
        lines = []
        for window in connection.windows():
            target = today + timedelta(days=window)
            subscriptions = (
                subscriptions_for_owner(connection.owner_id).filter(
                    expires_at__date=target,
                )
                .select_related("client", "service")
                .order_by("expires_at")
            )
            for sub in subscriptions:
                when = "HOY" if window == 0 else f"en {window} día{'s' if window != 1 else ''}"
                lines.append(
                    f"• <b>{html.escape(sub.service.name)}</b> · {html.escape(sub.client.name)}\n"
                    f"  {when} · {timezone.localtime(sub.expires_at):%d/%m/%Y}"
                )
        if not lines:
            continue
        try:
            send_message(
                connection.chat_id,
                "🔔 <b>Resumen de vencimientos</b>\n\n" + "\n\n".join(lines),
            )
        except Exception:
            logger.exception("No se pudo enviar resumen al owner=%s", connection.owner_id)
            continue
        connection.last_digest_date = today
        connection.save(update_fields=["last_digest_date", "updated_at"])
        sent += 1
    return sent
