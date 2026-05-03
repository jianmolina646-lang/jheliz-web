"""Integración con Telegram Bot API (sin dependencias extra).

Tres usos principales:

1. **Notificaciones al admin** con botones inline para confirmar/rechazar
   Yape, marcar entregado, reenviar credenciales (signals/views).
2. **Webhook de Telegram** (`telegram_webhook` view) que procesa mensajes y
   callback queries en tiempo real, sin polling.
3. **Comandos admin**: `/yape`, `/cliente`, `/buscar`, `/hoy`, `/reporte`,
   `/resumen`. Comandos públicos: `/catalogo`, `/pedido <uuid>`, `/ayuda`.
"""

from __future__ import annotations

import html
import json
import logging
import time
from typing import Any, Iterable

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
ADMIN_BASE = "https://jhelizservicestv.xyz/jheliz-admin"


# ---------- Configuración ----------

def _token() -> str:
    return getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""


def _admin_chat_id() -> str:
    return str(getattr(settings, "TELEGRAM_ADMIN_CHAT_ID", "") or "")


def is_configured() -> bool:
    return bool(_token())


def _is_admin_chat(chat_id: int | str) -> bool:
    admin = _admin_chat_id()
    return bool(admin) and str(chat_id) == admin


# ---------- API low-level ----------

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


def _build_reply_markup(buttons: Iterable[Iterable[dict]] | None) -> dict | None:
    if not buttons:
        return None
    rows = []
    for row in buttons:
        rows.append([dict(b) for b in row])
    return {"inline_keyboard": rows}


def send_message(
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    buttons: Iterable[Iterable[dict]] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    markup = _build_reply_markup(buttons)
    if markup:
        payload["reply_markup"] = markup
    return _call("sendMessage", **payload)


def edit_message_text(
    chat_id: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    buttons: Iterable[Iterable[dict]] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    markup = _build_reply_markup(buttons)
    if markup is not None:
        payload["reply_markup"] = markup
    return _call("editMessageText", **payload)


def answer_callback_query(callback_query_id: str, text: str = "", alert: bool = False) -> dict:
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if alert:
        payload["show_alert"] = True
    return _call("answerCallbackQuery", **payload)


def set_webhook(url: str, secret_token: str = "") -> dict:
    payload: dict[str, Any] = {
        "url": url,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "callback_query"],
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return _call("setWebhook", **payload)


def delete_webhook() -> dict:
    return _call("deleteWebhook", drop_pending_updates=True)


def get_webhook_info() -> dict:
    return _call("getWebhookInfo")


# ---------- Notificaciones admin ----------

def notify_admin(text: str, buttons: Iterable[Iterable[dict]] | None = None) -> dict | None:
    chat_id = _admin_chat_id()
    if not (is_configured() and chat_id):
        return None
    try:
        return send_message(chat_id, text, buttons=buttons)
    except Exception:
        logger.exception("No se pudo notificar al admin por Telegram")
        return None


def _admin_url(path: str) -> str:
    return f"{ADMIN_BASE}{path}"


def order_action_buttons(order) -> list[list[dict]]:
    """Botones según el estado del pedido."""
    from .models import Order  # evita ciclo

    rows: list[list[dict]] = []
    if order.status == Order.Status.VERIFYING and order.payment_provider == "yape":
        rows.append([
            {"text": "✅ Confirmar Yape", "callback_data": f"yape:confirm:{order.pk}"},
            {"text": "❌ Rechazar", "callback_data": f"yape:reject:{order.pk}"},
        ])
    if order.status in {Order.Status.PAID, Order.Status.PREPARING, Order.Status.VERIFYING}:
        rows.append([
            {"text": "📦 Marcar entregado (admin)",
             "url": _admin_url(f"/orders/order/{order.pk}/deliver/")},
        ])
    if order.status == Order.Status.DELIVERED:
        rows.append([
            {"text": "↻ Reenviar credenciales", "callback_data": f"order:resend:{order.pk}"},
        ])
    rows.append([
        {"text": "🔍 Ver pedido en admin",
         "url": _admin_url(f"/orders/order/{order.pk}/change/")},
    ])
    return rows


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
    return "\n".join(lines)


def format_yape_proof(order) -> str:
    return "\n".join([
        f"<b>💸 Comprobante Yape — pedido #{order.short_uuid}</b>",
        f"Cliente: {order.email or '(sin correo)'}"
        + (f" · tel {order.phone}" if order.phone else ""),
        f"Total: {order.currency} {order.total}",
        "",
        "Aprueba o rechaza desde aquí mismo:",
    ])


def notify_admin_about_order(order) -> None:
    notify_admin(format_new_order(order), buttons=order_action_buttons(order))


def notify_admin_about_yape(order) -> None:
    notify_admin(format_yape_proof(order), buttons=order_action_buttons(order))


# ---------- Canal público de avisos ----------

SITE_BASE = "https://jhelizservicestv.xyz"


def _channel_id() -> str:
    return str(getattr(settings, "TELEGRAM_CHANNEL_ID", "") or "")


def channel_is_configured() -> bool:
    return bool(is_configured() and _channel_id())


def post_to_channel(
    text: str,
    buttons: Iterable[Iterable[dict]] | None = None,
    photo_url: str = "",
) -> dict | None:
    """Publica un mensaje en el canal público.

    Si `photo_url` está, manda un sendPhoto con caption (HTML). Si no, un
    sendMessage normal.
    """
    chat_id = _channel_id()
    if not (is_configured() and chat_id):
        return None
    try:
        if photo_url:
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": text,
                "parse_mode": "HTML",
            }
            markup = _build_reply_markup(buttons)
            if markup:
                payload["reply_markup"] = markup
            return _call("sendPhoto", **payload)
        return send_message(chat_id, text, buttons=buttons)
    except Exception:
        logger.exception("No se pudo publicar en el canal de Telegram")
        return None


def _product_url(product) -> str:
    try:
        return f"{SITE_BASE}{product.get_absolute_url()}"
    except Exception:
        return f"{SITE_BASE}/productos/"


def _product_image_url(product) -> str:
    image = getattr(product, "image", None)
    if image and getattr(image, "url", ""):
        url = image.url
        if url.startswith("http"):
            return url
        return f"{SITE_BASE}{url}"
    return ""


def _product_button_row(product) -> list[dict]:
    return [{"text": "🛒 Ver en la web", "url": _product_url(product)}]


def _format_price_lines(product) -> list[str]:
    currency = getattr(settings, "DEFAULT_CURRENCY_SYMBOL", "S/")
    plans = product.plans.filter(
        is_active=True, available_for_customer=True,
    ).order_by("order", "duration_days")
    lines: list[str] = []
    for plan in plans:
        if plan.price_customer <= 0:
            continue
        duration = (
            f"{plan.duration_days} días" if plan.duration_days else "sin expiración"
        )
        lines.append(
            f"• {html.escape(plan.name)} ({duration}) — {currency} "
            f"{plan.price_customer:.2f}"
        )
    return lines


def format_product_announcement(product, kind: str = "new") -> str:
    """Genera el mensaje para un producto. ``kind`` ∈ {'new', 'restock'}."""
    safe_name = html.escape(product.name or "")
    title_map = {
        "new": f"🆕 <b>Nuevo: {safe_name}</b>",
        "restock": f"📦 <b>Volvió el stock — {safe_name}</b>",
    }
    lines = [title_map.get(kind, f"<b>{safe_name}</b>")]
    if product.short_description:
        lines.append(html.escape(product.short_description))
    price_lines = _format_price_lines(product)
    if price_lines:
        lines.append("")
        lines.extend(price_lines)
    lines.append("")
    lines.append("✅ Garantía durante toda la suscripción")
    lines.append("⚡ Entrega rápida")
    return "\n".join(lines)


def format_coupon_announcement(coupon) -> str:
    if coupon.discount_type == coupon.DiscountType.PERCENT:
        descuento = f"{coupon.discount_value:g}%"
    else:
        currency = getattr(settings, "DEFAULT_CURRENCY_SYMBOL", "S/")
        descuento = f"{currency} {coupon.discount_value:g}"
    lines = [
        f"💰 <b>Cupón nuevo: {html.escape(coupon.code)}</b>",
        f"Descuento: <b>{html.escape(descuento)}</b>",
    ]
    if getattr(coupon, "min_order_total", 0):
        lines.append(f"Compra mínima: S/ {coupon.min_order_total:g}")
    if getattr(coupon, "valid_until", None):
        lines.append(f"Válido hasta: {coupon.valid_until.strftime('%d/%m/%Y')}")
    lines.append("")
    lines.append("Aplica el código al pagar 👇")
    return "\n".join(lines)


def announce_product(product, kind: str = "new") -> dict | None:
    if not channel_is_configured():
        return None
    text = format_product_announcement(product, kind=kind)
    photo = _product_image_url(product)
    return post_to_channel(text, buttons=[_product_button_row(product)], photo_url=photo)


def announce_coupon(coupon) -> dict | None:
    if not channel_is_configured():
        return None
    text = format_coupon_announcement(coupon)
    return post_to_channel(text, buttons=[[{"text": "🛒 Ir a la tienda", "url": SITE_BASE}]])


def announce_text(text: str) -> dict | None:
    if not channel_is_configured():
        return None
    return post_to_channel(text)


# ---------- Comandos / handlers ----------

PUBLIC_HELP = (
    "👋 Soy el bot de <b>Jheliz</b>.\n\n"
    "<b>Comandos públicos</b>\n"
    "/catalogo — productos activos\n"
    "/pedido &lt;uuid&gt; — estado de un pedido\n"
    "/ayuda — esta ayuda"
)

ADMIN_HELP = PUBLIC_HELP + (
    "\n\n<b>Comandos admin</b>\n"
    "/yape — pedidos Yape pendientes (con botones)\n"
    "/avisar &lt;texto&gt; — publicar al canal Jheliz Avisos\n"
    "/canal — info del canal y plantillas\n"
    "/hoy — pedidos de hoy\n"
    "/cliente &lt;email|tel&gt; — ficha rápida\n"
    "/buscar &lt;texto&gt; — productos\n"
    "/reporte — ventas semana / mes\n"
    "/resumen — resumen diario al instante"
)


def _handle_message(update: dict) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    is_admin = _is_admin_chat(chat_id)
    cmd, _, rest = text.partition(" ")
    cmd = cmd.lower().split("@", 1)[0]  # quita @botname si lo hubiera
    rest = rest.strip()

    # Públicos
    if cmd in ("/start", "/ayuda", "/help"):
        send_message(chat_id, ADMIN_HELP if is_admin else PUBLIC_HELP)
        return
    if cmd == "/catalogo":
        _cmd_catalogo(chat_id)
        return
    if cmd == "/pedido":
        _cmd_pedido(chat_id, rest)
        return

    # Admin only
    if not is_admin:
        send_message(chat_id, PUBLIC_HELP)
        return

    if cmd == "/yape":
        _cmd_yape(chat_id)
        return
    if cmd == "/hoy":
        _cmd_hoy(chat_id)
        return
    if cmd == "/cliente":
        _cmd_cliente(chat_id, rest)
        return
    if cmd == "/buscar":
        _cmd_buscar(chat_id, rest)
        return
    if cmd == "/reporte":
        _cmd_reporte(chat_id)
        return
    if cmd == "/resumen":
        send_message(chat_id, daily_summary_text())
        return
    if cmd == "/avisar":
        _cmd_avisar(chat_id, rest)
        return
    if cmd == "/canal":
        _cmd_canal(chat_id)
        return

    send_message(chat_id, ADMIN_HELP)


def _handle_callback_query(update: dict) -> None:
    cq = update.get("callback_query") or {}
    cq_id = cq.get("id") or ""
    data = (cq.get("data") or "").strip()
    chat = (cq.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    message_id = (cq.get("message") or {}).get("message_id")
    # Telegram nos devuelve el texto del mensaje original sin formato HTML;
    # lo escapamos antes de re-enviarlo como HTML para evitar fallos de parseo
    # cuando el contenido tiene `<`, `>` o `&` (ej. nombres con `&`).
    original_text = html.escape((cq.get("message") or {}).get("text") or "")

    if not _is_admin_chat(chat_id):
        answer_callback_query(cq_id, "Sin permiso.", alert=True)
        return

    parts = data.split(":")
    if len(parts) < 3:
        answer_callback_query(cq_id, "Acción inválida.")
        return
    domain, action, raw_pk = parts[0], parts[1], parts[2]
    try:
        pk = int(raw_pk)
    except ValueError:
        answer_callback_query(cq_id, "ID inválido.")
        return

    from .models import Order
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        answer_callback_query(cq_id, "Pedido no encontrado.", alert=True)
        return

    if domain == "yape" and action == "confirm":
        _callback_yape_confirm(order, chat_id, message_id, original_text, cq_id)
    elif domain == "yape" and action == "reject":
        _callback_yape_reject(order, chat_id, message_id, original_text, cq_id)
    elif domain == "order" and action == "resend":
        _callback_order_resend(order, chat_id, message_id, original_text, cq_id)
    else:
        answer_callback_query(cq_id, "Acción no soportada.")


def _callback_yape_confirm(order, chat_id, message_id, original_text, cq_id):
    from .yape_actions import confirm_yape_payment

    result = confirm_yape_payment(order)
    if not result.ok:
        answer_callback_query(cq_id, result.message[:180], alert=True)
        return
    answer_callback_query(cq_id, "Pago Yape confirmado ✅")
    edit_message_text(
        chat_id,
        message_id,
        original_text + f"\n\n<b>✅ {result.message}</b>",
        buttons=[[{
            "text": "🔍 Ver pedido en admin",
            "url": _admin_url(f"/orders/order/{order.pk}/change/"),
        }]],
    )


def _callback_yape_reject(order, chat_id, message_id, original_text, cq_id):
    """Rechaza con el motivo genérico. Para motivos personalizados, abrir admin."""
    from .yape_actions import reject_yape_payment

    result = reject_yape_payment(
        order,
        reason=(
            "No pudimos verificar el comprobante. Por favor sube una captura "
            "más clara donde se vea el monto y el destinatario."
        ),
    )
    if not result.ok:
        answer_callback_query(cq_id, result.message[:180], alert=True)
        return
    answer_callback_query(cq_id, "Comprobante rechazado")
    edit_message_text(
        chat_id,
        message_id,
        original_text + "\n\n<b>❌ Comprobante rechazado y cliente notificado.</b>",
        buttons=[[{
            "text": "🔍 Ver pedido en admin",
            "url": _admin_url(f"/orders/order/{order.pk}/change/"),
        }]],
    )


def _callback_order_resend(order, chat_id, message_id, original_text, cq_id):
    from . import emails
    from .models import Order

    if order.status != Order.Status.DELIVERED:
        answer_callback_query(cq_id, "Solo se reenvía cuando ya está entregado.", alert=True)
        return
    try:
        emails.send_order_delivered(order)
    except Exception:
        logger.exception("Falló reenvío de credenciales")
        answer_callback_query(cq_id, "No se pudo reenviar.", alert=True)
        return
    answer_callback_query(cq_id, "Credenciales reenviadas ✉️")
    edit_message_text(
        chat_id,
        message_id,
        original_text + "\n\n<b>↻ Credenciales reenviadas al cliente.</b>",
        buttons=[[{
            "text": "🔍 Ver pedido en admin",
            "url": _admin_url(f"/orders/order/{order.pk}/change/"),
        }]],
    )


# ---------- Implementación de comandos ----------

def _cmd_catalogo(chat_id: int | str) -> None:
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
    lines.append("Compra en https://jhelizservicestv.xyz/productos/")
    send_message(chat_id, "\n".join(lines))


def _cmd_pedido(chat_id: int | str, rest: str) -> None:
    from .models import Order

    uid = rest.strip()
    if not uid:
        send_message(chat_id, "Usa: <code>/pedido &lt;uuid&gt;</code>")
        return
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
        f"https://jhelizservicestv.xyz/pedidos/{order.uuid}/",
    )


def _cmd_yape(chat_id: int | str) -> None:
    from .models import Order

    qs = (Order.objects
          .filter(status=Order.Status.VERIFYING, payment_provider="yape")
          .order_by("-payment_proof_uploaded_at")[:10])
    items = list(qs)
    if not items:
        send_message(chat_id, "Sin Yape pendientes 🎉")
        return
    send_message(chat_id, f"<b>Yape pendientes ({len(items)})</b>")
    for o in items:
        notify_admin_about_yape(o)


def _cmd_hoy(chat_id: int | str) -> None:
    from django.utils import timezone
    from .models import Order

    today = timezone.localdate()
    qs = Order.objects.filter(created_at__date=today).order_by("-created_at")[:25]
    items = list(qs)
    if not items:
        send_message(chat_id, "Hoy aún no hay pedidos.")
        return
    lines = [f"<b>Pedidos de hoy ({len(items)})</b>", ""]
    for o in items:
        lines.append(
            f"• #{o.short_uuid} · {o.get_status_display()} · "
            f"{o.currency} {o.total} · {o.email or 'sin correo'}"
        )
    lines.append("")
    lines.append(f"{ADMIN_BASE}/orders/order/")
    send_message(chat_id, "\n".join(lines))


def _cmd_cliente(chat_id: int | str, rest: str) -> None:
    from .models import Order

    q = rest.strip()
    if not q:
        send_message(chat_id, "Usa: <code>/cliente &lt;email o teléfono&gt;</code>")
        return
    qs = Order.objects.filter(email__iexact=q) | Order.objects.filter(phone__icontains=q)
    qs = qs.order_by("-created_at")[:5]
    items = list(qs)
    if not items:
        send_message(chat_id, f"No encontré pedidos para <code>{q}</code>.")
        return
    total = sum((o.total for o in items), start=type(items[0].total)(0))
    lines = [
        f"<b>Cliente {q}</b>",
        f"{len(items)} pedido(s) · total mostrado: {items[0].currency} {total}",
        "",
    ]
    for o in items:
        lines.append(
            f"• #{o.short_uuid} · {o.get_status_display()} · "
            f"{o.currency} {o.total} · {o.created_at:%d/%m %H:%M}"
        )
    send_message(chat_id, "\n".join(lines))


def _cmd_buscar(chat_id: int | str, rest: str) -> None:
    from catalog.models import Product

    q = rest.strip()
    if not q:
        send_message(chat_id, "Usa: <code>/buscar &lt;texto&gt;</code>")
        return
    qs = Product.objects.filter(name__icontains=q, is_active=True)[:15]
    items = list(qs)
    if not items:
        send_message(chat_id, f"Sin resultados para <code>{q}</code>.")
        return
    lines = [f"<b>Resultados para «{q}»</b>", ""]
    for p in items:
        plan = p.plans.filter(is_active=True).order_by("price_customer").first()
        precio = f"{settings.DEFAULT_CURRENCY_SYMBOL} {plan.price_customer:.2f}" if plan else "—"
        lines.append(f"• <b>{p.name}</b> desde {precio}")
    send_message(chat_id, "\n".join(lines))


def _cmd_reporte(chat_id: int | str) -> None:
    send_message(chat_id, _report_text())


def _cmd_avisar(chat_id: int | str, text: str) -> None:
    if not channel_is_configured():
        send_message(chat_id, "TELEGRAM_CHANNEL_ID no configurado en .env.")
        return
    text = (text or "").strip()
    if not text:
        send_message(
            chat_id,
            "Uso: <code>/avisar &lt;texto&gt;</code>\n"
            "Ejemplo: <code>/avisar Netflix está caído, lo reactivamos en 1 hora.</code>",
        )
        return
    result = announce_text(text)
    if result and result.get("ok"):
        send_message(chat_id, "✅ Publicado en el canal.")
    else:
        send_message(chat_id, f"❌ No se pudo publicar: {result}")


def _cmd_canal(chat_id: int | str) -> None:
    if not channel_is_configured():
        send_message(
            chat_id,
            "Canal sin configurar. Define <code>TELEGRAM_CHANNEL_ID</code> en .env "
            "y reinicia.",
        )
        return
    send_message(
        chat_id,
        f"📣 <b>Canal de avisos</b>\n"
        f"Destino: <code>{_channel_id()}</code>\n\n"
        "Auto-publicación:\n"
        "• 🆕 Producto activado en el admin\n"
        "• 📦 Stock repuesto (de 0 a ≥1) en un plan\n"
        "• 💰 Cupón nuevo activo\n\n"
        "Manual:\n"
        "• /avisar &lt;texto&gt; desde este chat\n"
        "• Botón <i>“Publicar al canal”</i> en cada producto del admin",
    )


# ---------- Resumen / reporte ----------

def _money_sum(qs) -> tuple[str, str]:
    """Devuelve (currency, formatted_total) para un queryset de Order."""
    items = list(qs)
    if not items:
        return ("PEN", "0.00")
    total = sum((o.total for o in items), start=type(items[0].total)(0))
    return (items[0].currency or "PEN", f"{total:.2f}")


def _report_text() -> str:
    from datetime import timedelta
    from django.utils import timezone
    from .models import Order

    today = timezone.localdate()
    week_start = today - timedelta(days=7)
    month_start = today.replace(day=1)

    paid = Order.objects.filter(status__in=[
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    ])
    today_qs = paid.filter(created_at__date=today)
    week_qs = paid.filter(created_at__date__gte=week_start)
    month_qs = paid.filter(created_at__date__gte=month_start)

    cur_t, t_today = _money_sum(today_qs)
    _, t_week = _money_sum(week_qs)
    _, t_month = _money_sum(month_qs)

    return "\n".join([
        "<b>📊 Reporte Jheliz</b>",
        f"Hoy: {today_qs.count()} pedidos · {cur_t} {t_today}",
        f"Últimos 7 días: {week_qs.count()} pedidos · {cur_t} {t_week}",
        f"Mes en curso: {month_qs.count()} pedidos · {cur_t} {t_month}",
    ])


def daily_summary_text() -> str:
    """Resumen para el cron de las 8am."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import Order

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    paid_states = [Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED]
    yest_qs = Order.objects.filter(created_at__date=yesterday, status__in=paid_states)
    cur, t_yest = _money_sum(yest_qs)

    pending_yape = Order.objects.filter(
        status=Order.Status.VERIFYING, payment_provider="yape",
    ).count()
    pending_prep = Order.objects.filter(status=Order.Status.PREPARING).count()

    # Tickets abiertos
    open_tickets = 0
    try:
        from accounts.models import Ticket  # type: ignore

        open_tickets = Ticket.objects.exclude(status="closed").count()
    except Exception:
        pass

    # Stock crítico
    low_stock_lines: list[str] = []
    try:
        from catalog.models import Plan  # type: ignore

        for plan in Plan.objects.filter(is_active=True).select_related("product")[:200]:
            available = getattr(plan, "available_stock", None)
            if callable(available):
                qty = available()
            else:
                qty = available
            if qty is None:
                continue
            if qty <= 1:
                low_stock_lines.append(
                    f"  · {plan.product.name} — {plan.name}: {qty}"
                )
            if len(low_stock_lines) >= 6:
                break
    except Exception:
        pass

    lines = [
        "🌅 <b>Resumen diario Jheliz</b>",
        "",
        f"<b>Ayer</b>: {yest_qs.count()} pedidos · {cur} {t_yest}",
        f"<b>Yape por verificar</b>: {pending_yape}",
        f"<b>Pedidos en preparación</b>: {pending_prep}",
        f"<b>Tickets abiertos</b>: {open_tickets}",
    ]
    if low_stock_lines:
        lines.append("")
        lines.append("<b>Stock crítico (≤1):</b>")
        lines.extend(low_stock_lines)
    lines.append("")
    lines.append(f"🔗 {ADMIN_BASE}/")
    return "\n".join(lines)


# ---------- Polling (legacy, sigue disponible) ----------

def run_polling(poll_interval: float = 1.0) -> None:
    """Long polling (alternativa al webhook). Sólo si no se configura webhook."""
    if not is_configured():
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
    offset = 0
    logger.info("Bot Jheliz iniciado (long polling)")
    while True:
        try:
            data = _call(
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    process_update(upd)
                except Exception:
                    logger.exception("Error procesando update")
        except requests.RequestException:
            logger.warning("Telegram getUpdates falló, reintentando…")
        # Sleep incondicional para evitar tight-loop si Telegram devuelve
        # respuestas erróneas sin levantar excepción (token revocado, rate
        # limit, etc.).
        time.sleep(poll_interval)


def process_update(update: dict) -> None:
    """Punto de entrada único: lo usan webhook y polling."""
    if "callback_query" in update:
        _handle_callback_query(update)
    else:
        _handle_message(update)


# Compatibilidad con tests viejos
_handle_update = _handle_message


def parse_update_payload(body: bytes | str) -> dict:
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    try:
        return json.loads(body)
    except Exception:
        return {}
