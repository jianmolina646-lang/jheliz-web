"""Integración ligera con Telegram Bot API usando requests (sin dependencia extra).

Dos usos principales:

1. **Notificaciones al admin** cuando llega un pedido nuevo (llamado desde señales/webhook).
2. **Bot para clientes** con comandos básicos (`/start`, `/catalogo`, `/pedido <uuid>`).
   Se arranca con `python manage.py run_telegram_bot` (long polling).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""


def is_configured() -> bool:
    return bool(_token())


def _call(method: str, **payload) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, json=payload, timeout=30)
    data: dict[str, Any]
    try:
        data = resp.json()
    except ValueError:
        data = {"ok": False, "description": resp.text}
    if not data.get("ok"):
        logger.warning("Telegram %s falló: %s", method, data)
    return data


def send_message(chat_id: str | int, text: str, parse_mode: str = "HTML") -> dict:
    return _call(
        "sendMessage",
        chat_id=str(chat_id),
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )


def notify_admin(text: str) -> None:
    chat_id = getattr(settings, "TELEGRAM_ADMIN_CHAT_ID", "") or ""
    if not (is_configured() and chat_id):
        return
    try:
        send_message(chat_id, text)
    except Exception:
        logger.exception("No se pudo notificar al admin por Telegram")


def format_new_order(order) -> str:
    lines = [
        f"<b>Nuevo pedido #{order.short_uuid}</b>",
        f"Cliente: {order.email or '(sin correo)'}"
        + (f" · tel {order.phone}" if order.phone else ""),
        f"Total: {order.currency} {order.total}",
        f"Estado: {order.get_status_display()}",
        "",
        "<b>Items</b>",
    ]
    for it in order.items.all():
        lines.append(f"• {it.product_name} — {it.plan_name} × {it.quantity}")
        if it.requested_profile_name or it.requested_pin:
            lines.append(
                f"   Perfil: <b>{it.requested_profile_name or '-'}</b> · "
                f"PIN: <b>{it.requested_pin or '-'}</b>"
            )
        if it.customer_notes:
            lines.append(f"   Notas: {it.customer_notes}")
    lines.append("")
    lines.append(f"🔗 https://jhelizservicestv.es/jheliz-admin/orders/order/{order.pk}/change/")
    return "\n".join(lines)


# -------- Polling bot --------

HELP_TEXT = (
    "👋 Soy el bot de <b>Jheliz</b>. Comandos:\n"
    "/catalogo — ver productos\n"
    "/pedido &lt;uuid&gt; — estado de un pedido\n"
    "/ayuda — este mensaje"
)


def _handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text.startswith("/start"):
        send_message(chat_id, HELP_TEXT)
        return
    if text.startswith("/ayuda") or text.startswith("/help"):
        send_message(chat_id, HELP_TEXT)
        return
    if text.startswith("/catalogo"):
        from catalog.models import Product

        products = Product.objects.filter(is_active=True)[:20]
        if not products:
            send_message(chat_id, "Todavía no hay productos cargados.")
            return
        lines = ["<b>Catálogo Jheliz</b>", ""]
        for p in products:
            plan = p.plans.filter(is_active=True).order_by("price_customer").first()
            precio = (
                f"{settings.DEFAULT_CURRENCY_SYMBOL} {plan.price_customer:.2f}"
                if plan
                else "—"
            )
            lines.append(f"• <b>{p.name}</b> desde {precio}")
        lines.append("")
        lines.append("Compra en https://jhelizservicestv.es/productos/")
        send_message(chat_id, "\n".join(lines))
        return
    if text.startswith("/pedido"):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            send_message(chat_id, "Usa: <code>/pedido &lt;uuid&gt;</code>")
            return
        from orders.models import Order

        uid = parts[1].strip()
        try:
            order = Order.objects.get(uuid=uid)
        except (Order.DoesNotExist, ValueError):
            send_message(chat_id, f"No encontré el pedido <code>{uid}</code>.")
            return
        send_message(
            chat_id,
            f"Pedido <b>#{order.short_uuid}</b>\n"
            f"Estado: <b>{order.get_status_display()}</b>\n"
            f"Total: {order.currency} {order.total}\n"
            f"https://jhelizservicestv.es/pedidos/{order.uuid}/",
        )
        return

    send_message(chat_id, HELP_TEXT)


def run_polling(poll_interval: float = 1.0) -> None:
    """Corre un bucle simple de long polling."""
    if not is_configured():
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
    offset = 0
    logger.info("Bot Jheliz iniciado (long polling)")
    while True:
        try:
            data = _call("getUpdates", offset=offset, timeout=25)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    _handle_update(upd)
                except Exception:
                    logger.exception("Error procesando update")
        except requests.RequestException:
            logger.exception("Error en getUpdates, reintentando…")
            time.sleep(5)
        time.sleep(poll_interval)
