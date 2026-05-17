"""Helpers de alto nivel para mandar avisos al back-office en Discord.

Cada función está pensada para reemplazar 1:1 una notificación que hoy va
a Telegram (al canal de distribuidores o al DM admin). Si el bot no está
configurado, devuelven ``None`` sin romper nada.

Funciones públicas:

- ``is_backoffice_configured()`` — True si hay token + canal de pedidos.
- ``notify_new_code_request(request, code_request)`` — pedidos de código.
- ``notify_new_order(order)`` — pedido nuevo, crea thread por pedido.
- ``notify_yape_pending(order)`` — comprobante de Yape/Binance recibido.
- ``notify_order_status_change(order, prev_status)`` — cambio de estado.
- ``notify_stock_low(product, total, threshold)`` — alerta de stock.
- ``notify_admin_generic(text)`` — fallback genérico al canal #admin.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.urls import reverse

from . import client

logger = logging.getLogger(__name__)


# Paleta de colores semánticos para los embeds (modo oscuro de Discord).
COLOR_INFO = 0x6366F1     # índigo: notificación neutral
COLOR_SUCCESS = 0x22C55E  # verde
COLOR_WARNING = 0xF59E0B  # ámbar: acción requerida
COLOR_DANGER = 0xEF4444   # rojo: error / rechazo
COLOR_PURPLE = 0xA855F7   # morado: marca Jheliz


# ---------- Helpers internos ----------

def _admin_url(request, view_name: str, *args) -> str:
    """Construye un URL absoluto al admin (para botones link)."""
    if request is not None:
        try:
            return request.build_absolute_uri(reverse(view_name, args=args))
        except Exception:
            pass
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    try:
        path = reverse(view_name, args=args)
    except Exception:
        return base or ""
    return f"{base}{path}"


def _site_url(path: str = "") -> str:
    base = getattr(settings, "SITE_URL", "").rstrip("/") or "https://ecormecejhelizstore.com"
    return f"{base}{path}"


def _channel(name: str) -> str:
    """Devuelve el ID del canal configurado o "" si no hay."""
    mapping = {
        "pedidos": getattr(settings, "DISCORD_CHANNEL_PEDIDOS", ""),
        "yape": getattr(settings, "DISCORD_CHANNEL_YAPE", ""),
        "codigos": getattr(settings, "DISCORD_CHANNEL_CODIGOS", ""),
        "alertas": getattr(settings, "DISCORD_CHANNEL_ALERTAS", ""),
        "admin": getattr(settings, "DISCORD_CHANNEL_ADMIN", ""),
    }
    return str(mapping.get(name, "") or "")


def is_backoffice_configured() -> bool:
    """¿Está el bot listo para manejar el back-office?

    Requiere token + canal de pedidos. Si está True, los callers que hoy
    notifican a Telegram pueden redirigir a Discord sin riesgo.
    """
    return client.is_configured() and bool(_channel("pedidos"))


# ---------- API pública ----------

def notify_test(channel_key: str = "admin", message: str = "🔔 Test de conexión Discord ✓") -> dict | None:
    """Manda un mensaje de prueba al canal indicado."""
    if not client.is_configured():
        return None
    cid = _channel(channel_key)
    if not cid:
        return None
    return client.send_message(cid, message)


def notify_admin_generic(text: str) -> dict | None:
    """Envía un mensaje libre al canal #admin (fallback)."""
    if not client.is_configured():
        return None
    cid = _channel("admin")
    if not cid:
        return None
    return client.send_message(cid, text[:1900])


# ---------- Pedidos de código ----------

def notify_new_code_request(request, code_request) -> dict | None:
    """Aviso de nuevo pedido de código (del verificador `/codigos/`)."""
    if not client.is_configured():
        return None
    cid = _channel("codigos")
    if not cid:
        return None

    admin_url = _admin_url(
        request, "admin:support_coderequest_change", code_request.pk,
    )
    fields: list[dict[str, Any]] = [
        {"name": "Plataforma", "value": code_request.get_platform_display(), "inline": True},
        {"name": "Cuenta", "value": f"`{code_request.account_email}`", "inline": True},
        {"name": "Origen", "value": code_request.get_audience_display(), "inline": True},
    ]
    if code_request.requested_code_type:
        fields.append({
            "name": "Pide",
            "value": code_request.get_requested_code_type_display(),
            "inline": False,
        })
    if code_request.order_number:
        fields.append({
            "name": "N° pedido",
            "value": f"`{code_request.order_number}`",
            "inline": True,
        })
    if code_request.note:
        fields.append({
            "name": "Nota del cliente",
            "value": code_request.note[:1024],
            "inline": False,
        })

    components = [client.action_row(
        client.link_button("Responder ahora", admin_url, emoji="✉️"),
    )]
    return client.send_embed(
        cid,
        title="🔔 Nuevo pedido de código",
        fields=fields,
        color=COLOR_WARNING,
        components=components,
        footer="Verificador de códigos · Jheliz",
    )


# ---------- Pedidos ----------

def _status_emoji(status: str) -> str:
    return {
        "pending": "🕒",
        "verifying": "🔎",
        "paid": "💳",
        "preparing": "🛠️",
        "delivered": "✅",
        "rejected": "❌",
        "cancelled": "🚫",
        "refunded": "↩️",
        "expired": "⌛",
    }.get(status or "", "📦")


def _status_color(status: str) -> int:
    return {
        "pending": COLOR_INFO,
        "verifying": COLOR_WARNING,
        "paid": COLOR_SUCCESS,
        "preparing": COLOR_PURPLE,
        "delivered": COLOR_SUCCESS,
        "rejected": COLOR_DANGER,
        "cancelled": COLOR_DANGER,
        "refunded": COLOR_DANGER,
        "expired": COLOR_DANGER,
    }.get(status or "", COLOR_INFO)


def _build_order_embed(order, *, title_prefix: str = "🛒") -> dict[str, Any]:
    """Construye el embed con los datos del pedido (productos, totales, cliente)."""
    fields: list[dict] = []
    items_lines: list[str] = []
    for it in order.items.all()[:10]:
        line = (
            f"• **{it.product_name}** — {it.plan_name} × {it.quantity}"
        )
        if it.requested_profile_name or it.requested_pin:
            line += (
                f"\n  Perfil: `{it.requested_profile_name or '—'}` · "
                f"PIN: `{it.requested_pin or '—'}`"
            )
        if it.customer_notes:
            note = (it.customer_notes or "")[:200]
            line += f"\n  📝 {note}"
        items_lines.append(line)
    items_value = "\n".join(items_lines) or "(sin items)"
    if len(items_value) > 1024:
        items_value = items_value[:1020] + "…"

    fields.append({"name": "🛍️ Items", "value": items_value, "inline": False})

    cliente_value = []
    if order.email:
        cliente_value.append(f"📧 `{order.email}`")
    if order.phone:
        cliente_value.append(f"📱 {order.phone}")
    if cliente_value:
        fields.append({
            "name": "👤 Cliente",
            "value": "\n".join(cliente_value),
            "inline": True,
        })

    total_line = f"**{order.currency} {order.total}**"
    method = (order.payment_provider or "—").title()
    fields.append({
        "name": "💰 Total",
        "value": f"{total_line}\n_via_ {method}",
        "inline": True,
    })

    status_value = (
        f"{_status_emoji(order.status)} **{order.get_status_display()}**"
    )
    fields.append({"name": "📊 Estado", "value": status_value, "inline": True})

    description = ""
    if getattr(order, "created_at", None):
        from django.utils import timezone
        try:
            local = timezone.localtime(order.created_at)
            description = f"<t:{int(local.timestamp())}:R>"  # "hace X min"
        except Exception:
            pass

    return {
        "title": f"{title_prefix}  Pedido `#{order.display_number}`",
        "description": description,
        "fields": fields,
        "color": _status_color(order.status),
    }


def _order_admin_buttons(order) -> list[dict]:
    """Botones link al admin para acciones sobre el pedido."""
    base = getattr(settings, "SITE_URL", "").rstrip("/") or "https://ecormecejhelizstore.com"
    admin_path = "/" + str(
        getattr(settings, "ADMIN_URL_PATH", "panel-jheliz-2026"),
    ).strip("/")
    view_url = f"{base}{admin_path}/orders/order/{order.pk}/change/"
    deliver_url = f"{base}{admin_path}/orders/order/{order.pk}/deliver/"

    row = [client.link_button("Ver en admin", view_url, emoji="🔍")]
    # Solo mostrar "Entregar" si el pedido aún no está entregado.
    if order.status not in ("delivered", "refunded", "cancelled", "rejected"):
        row.append(client.link_button("Entregar", deliver_url, emoji="📦"))
    return [client.action_row(*row[:5])]


def notify_new_order(order) -> dict | None:
    """Postea el pedido en #pedidos-nuevos y abre un thread por pedido.

    Persiste el ``DiscordOrderThread`` en BD para que ``notify_order_status_change``
    pueda postear actualizaciones dentro del mismo thread (en vez de
    inundar el canal con avisos sueltos).
    """
    if not is_backoffice_configured():
        return None
    cid = _channel("pedidos")
    if not cid:
        return None

    from .models import DiscordOrderThread

    # Si ya hay un thread, no duplicar.
    if hasattr(order, "discord_thread") and order.discord_thread:
        return None

    embed_data = _build_order_embed(order, title_prefix="🛒")
    components = _order_admin_buttons(order)
    msg = client.send_embed(
        cid,
        title=embed_data["title"],
        description=embed_data["description"],
        fields=embed_data["fields"],
        color=embed_data["color"],
        components=components,
        footer="Jheliz · Back-office",
    )
    if not msg:
        return None

    # Abrir thread.
    items_qs = list(order.items.all()[:1])
    first_label = items_qs[0].product_name if items_qs else "Pedido"
    thread_name = f"{order.display_number} · {first_label[:50]} · {order.currency} {order.total}"
    thread = client.start_thread_from_message(
        cid, msg["id"], thread_name,
    )
    if thread:
        DiscordOrderThread.objects.create(
            order=order,
            channel_id=cid,
            thread_id=str(thread.get("id", "")),
            root_message_id=str(msg.get("id", "")),
            last_status_posted=order.status or "",
        )
    return msg


def notify_yape_pending(order) -> dict | None:
    """Postea el comprobante en #yape-pendientes (o en el thread del pedido).

    Adjunta la imagen del comprobante via ``embed.image`` con la URL
    pública del archivo (Discord la descarga sola, igual que hacíamos con
    Telegram). Si el pedido ya tiene thread, además publica una copia
    dentro del thread para que toda la actividad del pedido quede unida.
    """
    if not is_backoffice_configured():
        return None
    cid = _channel("yape")
    if not cid:
        return None

    proof_url = ""
    try:
        if order.payment_proof:
            proof_url = _site_url(order.payment_proof.url)
    except Exception:
        proof_url = ""

    fields = [
        {"name": "👤 Cliente", "value": f"📧 `{order.email or '—'}`", "inline": True},
        {"name": "💰 Total", "value": f"**{order.currency} {order.total}**", "inline": True},
        {"name": "💳 Método", "value": (order.payment_provider or "—").title(), "inline": True},
    ]
    if order.payment_reference:
        fields.append({
            "name": "Referencia",
            "value": f"`{order.payment_reference}`",
            "inline": False,
        })

    base = getattr(settings, "SITE_URL", "").rstrip("/") or "https://ecormecejhelizstore.com"
    admin_path = "/" + str(
        getattr(settings, "ADMIN_URL_PATH", "panel-jheliz-2026"),
    ).strip("/")
    inbox_url = f"{base}{admin_path}/orders/order/?status__exact=verifying"
    order_url = f"{base}{admin_path}/orders/order/{order.pk}/change/"
    components = [client.action_row(
        client.link_button("Bandeja Yape", inbox_url, emoji="📥"),
        client.link_button("Ver pedido", order_url, emoji="🔍"),
    )]

    main = client.send_embed(
        cid,
        title=f"💸  Comprobante recibido · `#{order.display_number}`",
        fields=fields,
        color=COLOR_WARNING,
        image_url=proof_url or None,
        components=components,
        footer="Aprobá o rechazá desde la bandeja",
    )

    # Eco dentro del thread del pedido (si existe).
    try:
        thread = getattr(order, "discord_thread", None)
        if thread:
            client.send_embed(
                str(thread.thread_id),
                title=f"💸 Comprobante recibido",
                description=f"Revisalo en {_channel_mention(cid)}.",
                color=COLOR_WARNING,
                image_url=proof_url or None,
            )
    except Exception:
        pass
    return main


def _channel_mention(channel_id: str) -> str:
    """Helper para mencionar un canal por ID en un mensaje (`<#1234...>`)."""
    cid = (channel_id or "").strip()
    return f"<#{cid}>" if cid else ""


def notify_order_status_change(order, prev_status: str = "") -> dict | None:
    """Notifica un cambio de estado en el thread del pedido.

    Si el pedido no tiene thread asociado (porque era anterior a la
    activación de Discord), se omite silenciosamente.
    """
    if not is_backoffice_configured():
        return None
    try:
        thread = getattr(order, "discord_thread", None)
    except Exception:
        thread = None
    if not thread:
        return None
    if (prev_status or "") == order.status:
        return None

    emoji = _status_emoji(order.status)
    label = order.get_status_display()
    title = f"{emoji} Estado → **{label}**"

    description = ""
    if prev_status:
        description = f"_de_ `{prev_status}` _→_ `{order.status}`"

    msg = client.send_embed(
        str(thread.thread_id),
        title=title,
        description=description,
        color=_status_color(order.status),
        footer="Cambio automático de estado",
    )
    if msg:
        thread.last_status_posted = order.status or ""
        thread.save(update_fields=["last_status_posted"])

        # Si quedó entregado/cancelado/refunded, archivamos el thread.
        if order.status in ("delivered", "cancelled", "rejected", "refunded"):
            client.archive_thread(str(thread.thread_id))
    return msg


# ---------- Stock / Alertas ----------

def notify_stock_low(
    product_name: str,
    total: int,
    threshold: int = 3,
    *,
    extra: str = "",
) -> dict | None:
    """Aviso de stock bajo en #alertas."""
    if not client.is_configured():
        return None
    cid = _channel("alertas")
    if not cid:
        return None

    fields = [
        {"name": "Producto", "value": product_name, "inline": True},
        {"name": "Stock", "value": f"**{total}** disponible(s)", "inline": True},
        {"name": "Umbral", "value": f"≤ {threshold}", "inline": True},
    ]
    if extra:
        fields.append({"name": "Nota", "value": extra[:1024], "inline": False})

    return client.send_embed(
        cid,
        title="⚠️ Stock bajo",
        fields=fields,
        color=COLOR_DANGER,
        footer="Recargá el stock cuanto antes",
    )
