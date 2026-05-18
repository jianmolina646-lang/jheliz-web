"""Dispatcher de slash commands y botones de Discord.

Discord postea un JSON a nuestro webhook (`/discord/interactions/`) cuando
alguien usa un slash command o aprieta un botón. La firma se verifica con
la PUBLIC KEY del bot (Ed25519). Esta verificación es obligatoria para
que Discord considere el endpoint válido.

Comandos implementados:

- ``/buscar <consulta>`` — busca pedidos por email / número JH-XXXX.
- ``/pendientes`` — lista los últimos 10 pedidos esperando acción.
- ``/entregar <numero>`` — abre el formulario de entrega del admin.
- ``/stock <producto>`` — muestra stock disponible de un plan.
- ``/stats [periodo]`` — métricas (hoy, ayer, semana, mes).
- ``/cliente <email>`` — perfil 360° de un cliente.

Botones interactivos (custom_id ``order:<accion>:<pk>``):

- ``order:deliver`` — marca el pedido como entregado.
- ``order:preparing`` — pasa el pedido a "en preparación".
- ``order:reject`` — rechaza el pedido.

Patrón: ``handle_interaction(payload)`` recibe el body parseado y devuelve
un dict listo para responder a Discord (mismo formato que el endpoint
HTTP de Discord espera). Se separa de las views para que sea testeable
sin Django.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Tipos de interacción que Discord manda al webhook.
INTERACTION_PING = 1
INTERACTION_APPLICATION_COMMAND = 2
INTERACTION_MESSAGE_COMPONENT = 3
INTERACTION_MODAL_SUBMIT = 5

# Tipos de respuesta que Discord acepta.
RESPONSE_PONG = 1
RESPONSE_CHANNEL_MESSAGE = 4
RESPONSE_DEFERRED_CHANNEL_MESSAGE = 5
RESPONSE_UPDATE_MESSAGE = 7

# Flag de mensaje "ephemeral" (sólo visible para quien lanzó el comando).
FLAG_EPHEMERAL = 1 << 6


# Catálogo de slash commands que registramos. Lo consume el management
# command ``discord_register_commands``.
COMMAND_DEFINITIONS = [
    {
        "name": "buscar",
        "description": "Busca pedidos por email o número (JH-0042).",
        "options": [
            {
                "name": "consulta",
                "description": "Email, teléfono o número JH-XXXX",
                "type": 3,  # STRING
                "required": True,
            },
        ],
    },
    {
        "name": "pendientes",
        "description": "Lista los pedidos pendientes de acción.",
    },
    {
        "name": "entregar",
        "description": "Abre el formulario de entrega de un pedido.",
        "options": [
            {
                "name": "numero",
                "description": "Número de pedido (ej. JH-0042 o 42)",
                "type": 3,
                "required": True,
            },
        ],
    },
    {
        "name": "stock",
        "description": "Muestra el stock disponible por producto.",
        "options": [
            {
                "name": "producto",
                "description": "Nombre o slug del producto",
                "type": 3,
                "required": False,
            },
        ],
    },
    {
        "name": "stats",
        "description": "Métricas del negocio (ventas, pedidos, conversión).",
        "options": [
            {
                "name": "periodo",
                "description": "hoy / ayer / semana / mes",
                "type": 3,
                "required": False,
                "choices": [
                    {"name": "Hoy", "value": "hoy"},
                    {"name": "Ayer", "value": "ayer"},
                    {"name": "Semana", "value": "semana"},
                    {"name": "Mes", "value": "mes"},
                ],
            },
        ],
    },
    {
        "name": "cliente",
        "description": "Perfil 360° de un cliente por email.",
        "options": [
            {
                "name": "email",
                "description": "Email del cliente",
                "type": 3,
                "required": True,
            },
        ],
    },
]


# ---------------------------------------------------------------------
# Helpers de respuesta
# ---------------------------------------------------------------------

def _ephemeral(text: str | None = None, embeds: list[dict] | None = None,
               components: list[dict] | None = None) -> dict[str, Any]:
    """Construye una respuesta efímera (solo visible para el usuario)."""
    data: dict[str, Any] = {"flags": FLAG_EPHEMERAL}
    if text is not None:
        data["content"] = text[:2000]
    if embeds is not None:
        data["embeds"] = embeds[:10]
    if components is not None:
        data["components"] = components
    return {"type": RESPONSE_CHANNEL_MESSAGE, "data": data}


def _options_dict(options: list[dict]) -> dict[str, Any]:
    return {opt["name"]: opt.get("value") for opt in (options or [])}


# ---------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------

def _parse_order_number(query: str) -> int | None:
    """Acepta '#JH-0042', 'jh-42', '42', '#42'. Devuelve el PK o None."""
    if not query:
        return None
    raw = query.strip().lower().lstrip("#").replace("jh-", "")
    if raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _admin_base() -> str:
    from django.conf import settings

    base = getattr(settings, "SITE_URL", "").rstrip("/") or "https://ecormecejhelizstore.com"
    path = "/" + str(
        getattr(settings, "ADMIN_URL_PATH", "panel-jheliz-2026"),
    ).strip("/")
    return f"{base}{path}"


def _format_order_line(order) -> str:
    items = list(order.items.all()[:1])
    label = items[0].product_name if items else "pedido"
    when = ""
    if getattr(order, "created_at", None):
        try:
            when = f" · <t:{int(order.created_at.timestamp())}:R>"
        except Exception:
            pass
    return (
        f"`#{order.display_number}` · **{label[:30]}** · "
        f"{order.currency} {order.total} · _{order.get_status_display()}_"
        f"{when}"
    )


def _cmd_buscar(data: dict) -> dict[str, Any]:
    from orders.models import Order

    options = _options_dict(data.get("options", []))
    query = (options.get("consulta") or "").strip()
    if not query:
        return _ephemeral("Decime qué buscar (email, teléfono o `JH-XXXX`).")

    qs = Order.objects.select_related().order_by("-created_at")
    pk = _parse_order_number(query)
    if pk is not None:
        qs = qs.filter(pk=pk)
    elif "@" in query:
        qs = qs.filter(email__iexact=query)
    else:
        qs = qs.filter(phone__icontains=query)

    items = list(qs[:5])
    if not items:
        return _ephemeral(f"Sin resultados para `{query[:100]}`.")

    lines = [_format_order_line(o) for o in items]
    embed = {
        "title": f"🔍 Resultados ({len(items)})",
        "description": "\n".join(lines),
        "color": 0x6366F1,
    }
    rows: list[dict] = []
    base = _admin_base()
    from . import client as dc

    for order in items[:3]:
        rows.append(dc.action_row(
            dc.link_button(
                f"Ver #{order.display_number}",
                f"{base}/orders/order/{order.pk}/change/",
                emoji="🔍",
            ),
        ))
    return _ephemeral(embeds=[embed], components=rows or None)


def _cmd_pendientes(data: dict) -> dict[str, Any]:
    from orders.models import Order

    pending_statuses = (
        Order.Status.PENDING,
        Order.Status.VERIFYING,
        Order.Status.PAID,
        Order.Status.PREPARING,
    )
    items = list(
        Order.objects
        .filter(status__in=pending_statuses)
        .order_by("created_at")[:10]
    )
    if not items:
        return _ephemeral("🎉 No hay pedidos pendientes. Todo entregado.")

    lines = [_format_order_line(o) for o in items]
    embed = {
        "title": f"📋 Pendientes ({len(items)})",
        "description": "\n".join(lines),
        "color": 0xF59E0B,
        "footer": {"text": "Ordenados del más viejo al más nuevo"},
    }
    return _ephemeral(embeds=[embed])


def _cmd_entregar(data: dict) -> dict[str, Any]:
    from orders.models import Order
    from . import client as dc

    options = _options_dict(data.get("options", []))
    raw = (options.get("numero") or "").strip()
    pk = _parse_order_number(raw)
    if pk is None:
        return _ephemeral(f"Formato inválido: `{raw[:50]}`. Usá `JH-0042` o `42`.")

    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return _ephemeral(f"No encontré el pedido `{raw}`.")

    base = _admin_base()
    deliver_url = f"{base}/orders/order/{order.pk}/deliver/"
    view_url = f"{base}/orders/order/{order.pk}/change/"

    embed = {
        "title": f"📦 Entregar `#{order.display_number}`",
        "description": _format_order_line(order),
        "color": 0xA855F7,
    }
    row = dc.action_row(
        dc.link_button("Entregar ahora", deliver_url, emoji="📦"),
        dc.link_button("Ver pedido", view_url, emoji="🔍"),
    )
    return _ephemeral(embeds=[embed], components=[row])


def _cmd_stock(data: dict) -> dict[str, Any]:
    from catalog.models import Plan

    options = _options_dict(data.get("options", []))
    query = (options.get("producto") or "").strip()
    qs = Plan.objects.select_related("product").order_by("product__name", "name")
    if query:
        qs = qs.filter(product__name__icontains=query) | qs.filter(
            product__slug__icontains=query,
        )

    items = list(qs[:15])
    if not items:
        return _ephemeral(f"Sin planes que matcheen `{query[:50] or 'todos'}`.")

    lines = []
    for plan in items:
        try:
            available = plan.available_stock
        except Exception:
            available = "?"
        emoji = "🟢" if isinstance(available, int) and available > 3 else "🔴"
        lines.append(f"{emoji} **{plan.product.name}** — {plan.name}: `{available}`")

    embed = {
        "title": f"📦 Stock ({len(items)})",
        "description": "\n".join(lines)[:4000],
        "color": 0x22C55E,
    }
    return _ephemeral(embeds=[embed])


def _period_range(period: str):
    """Devuelve (inicio, fin, label) para 'hoy' / 'ayer' / 'semana' / 'mes'."""
    from datetime import timedelta
    from django.utils import timezone

    now = timezone.localtime()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period = (period or "hoy").lower()
    if period == "ayer":
        start = today - timedelta(days=1)
        end = today
        label = "Ayer"
    elif period == "semana":
        start = today - timedelta(days=7)
        end = now
        label = "Últimos 7 días"
    elif period == "mes":
        start = today - timedelta(days=30)
        end = now
        label = "Últimos 30 días"
    else:
        start = today
        end = now
        label = "Hoy"
    return start, end, label


def _cmd_stats(data: dict) -> dict[str, Any]:
    from django.db.models import Count, Sum
    from orders.models import Order

    options = _options_dict(data.get("options", []))
    period = (options.get("periodo") or "hoy").strip().lower()
    start, end, label = _period_range(period)

    qs = Order.objects.filter(created_at__gte=start, created_at__lt=end)
    total = qs.count()
    by_status = dict(qs.values_list("status").annotate(n=Count("id")))

    paid_qs = qs.filter(
        status__in=(
            Order.Status.PAID,
            Order.Status.PREPARING,
            Order.Status.DELIVERED,
        ),
    )
    revenue_pen = paid_qs.filter(currency="PEN").aggregate(s=Sum("total"))["s"] or 0
    revenue_usd = paid_qs.filter(currency="USD").aggregate(s=Sum("total"))["s"] or 0

    delivered = by_status.get(Order.Status.DELIVERED, 0)
    pendientes = sum(
        by_status.get(s, 0) for s in (
            Order.Status.PENDING, Order.Status.VERIFYING,
            Order.Status.PAID, Order.Status.PREPARING,
        )
    )

    conv_str = "—"
    if total:
        conv_pct = (delivered / total) * 100
        conv_str = f"{conv_pct:.0f}%"

    from orders.models import OrderItem
    top_items = list(
        OrderItem.objects.filter(order__in=paid_qs)
        .values("product_name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:3]
    )

    fields = [
        {"name": "📈 Pedidos", "value": f"**{total}** totales · {delivered} entregados · {pendientes} pendientes", "inline": False},
        {"name": "💰 Facturación", "value": f"**PEN {revenue_pen}** · USD {revenue_usd}", "inline": True},
        {"name": "🎯 Conversión", "value": f"**{conv_str}** (entregados/totales)", "inline": True},
    ]
    if top_items:
        top_str = "\n".join(
            f"`{i+1}.` **{it['product_name'][:30]}** — {it['qty']}"
            for i, it in enumerate(top_items)
        )
        fields.append({"name": "🏆 Top productos", "value": top_str, "inline": False})

    embed = {
        "title": f"📊 Stats · {label}",
        "color": 0x22C55E,
        "fields": fields,
        "footer": {"text": f"Período: {start.strftime('%d/%m %H:%M')} → {end.strftime('%d/%m %H:%M')}"},
    }
    return _ephemeral(embeds=[embed])


def _cmd_cliente(data: dict) -> dict[str, Any]:
    from django.db.models import Count, Max, Sum
    from orders.models import Order

    options = _options_dict(data.get("options", []))
    email = (options.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _ephemeral("Email inválido. Pasá un email tipo `cliente@correo.com`.")

    qs = Order.objects.filter(email__iexact=email)
    if not qs.exists():
        return _ephemeral(f"Sin pedidos para `{email}`.")

    paid_qs = qs.filter(
        status__in=(
            Order.Status.PAID,
            Order.Status.PREPARING,
            Order.Status.DELIVERED,
        ),
    )
    stats = qs.aggregate(
        n=Count("id"),
        last=Max("created_at"),
    )
    revenue_pen = paid_qs.filter(currency="PEN").aggregate(s=Sum("total"))["s"] or 0
    revenue_usd = paid_qs.filter(currency="USD").aggregate(s=Sum("total"))["s"] or 0

    last = stats["last"]
    last_str = f"<t:{int(last.timestamp())}:R>" if last else "—"

    history_lines: list[str] = []
    for o in qs.order_by("-created_at")[:5]:
        history_lines.append(_format_order_line(o))

    fields = [
        {"name": "📧 Email", "value": f"`{email}`", "inline": False},
        {"name": "📦 Pedidos", "value": f"**{stats['n']}** totales", "inline": True},
        {"name": "🕒 Último", "value": last_str, "inline": True},
        {"name": "💰 Gastado", "value": f"PEN {revenue_pen} · USD {revenue_usd}", "inline": True},
        {"name": "🧾 Historial", "value": ("\n".join(history_lines) or "—")[:1024], "inline": False},
    ]
    embed = {
        "title": "👤 Cliente 360°",
        "color": 0xA855F7,
        "fields": fields,
    }
    return _ephemeral(embeds=[embed])


_DISPATCHER = {
    "buscar": _cmd_buscar,
    "pendientes": _cmd_pendientes,
    "entregar": _cmd_entregar,
    "stock": _cmd_stock,
    "stats": _cmd_stats,
    "cliente": _cmd_cliente,
}


# ---------------------------------------------------------------------
# Botones (MESSAGE_COMPONENT)
# ---------------------------------------------------------------------

def _is_admin_user(user_id: str) -> bool:
    """¿El usuario que clickeó está autorizado a mutar pedidos?"""
    if not user_id:
        return False
    from django.conf import settings

    allowed = getattr(settings, "DISCORD_ADMIN_USER_IDS", "") or ""
    ids = {x.strip() for x in str(allowed).split(",") if x.strip()}
    if not ids:
        # Si la allowlist está vacía, no permitimos clicks (seguro por
        # defecto). Para habilitarla hay que setear DISCORD_ADMIN_USER_IDS
        # en el .env con tu user ID de Discord.
        return False
    return str(user_id) in ids


def _user_id_from_payload(payload: dict) -> str:
    """Discord manda el user en ``member.user.id`` (guild) o ``user.id`` (DM)."""
    member = payload.get("member") or {}
    user = (member.get("user") or {}) or payload.get("user") or {}
    return str(user.get("id", "")) if isinstance(user, dict) else ""


# Mapping action → (nuevo_status, etiqueta, color hex)
_ORDER_ACTIONS: dict[str, tuple[str, str, int]] = {
    "deliver": ("delivered", "✅ Entregado", 0x22C55E),
    "preparing": ("preparing", "🛠️ En preparación", 0xA855F7),
    "reject": ("rejected", "❌ Rechazado", 0xEF4444),
}


def _do_order_action(action: str, order_pk: int, user_id: str) -> dict[str, Any]:
    """Aplica la acción al pedido. Devuelve la respuesta a Discord."""
    if not _is_admin_user(user_id):
        return _ephemeral(
            "🚫 No estás autorizado para mutar pedidos desde Discord. "
            "Configurá `DISCORD_ADMIN_USER_IDS` en el `.env` con tu user ID."
        )

    target = _ORDER_ACTIONS.get(action)
    if not target:
        return _ephemeral(f"Acción desconocida: `{action}`.")
    new_status, label, color = target

    from django.utils import timezone
    from orders.models import Order

    try:
        order = Order.objects.get(pk=order_pk)
    except Order.DoesNotExist:
        return _ephemeral(f"No encontré el pedido `#{order_pk}`.")

    if order.status == new_status:
        return _ephemeral(f"Pedido `#{order.display_number}` ya está en estado **{label}**.")

    closed = ("delivered", "refunded", "cancelled", "rejected")
    if order.status in closed and new_status not in closed:
        return _ephemeral(
            f"No se puede reabrir un pedido en estado final "
            f"(`{order.get_status_display()}`)."
        )

    prev_status = order.status
    order.status = new_status
    update_fields = ["status"]
    if new_status == "delivered":
        order.delivered_at = timezone.now()
        update_fields.append("delivered_at")
    order.save(update_fields=update_fields)

    # Disparar avisos hacia el thread del pedido (si existe).
    try:
        from discord_bot import notifications as dn

        dn.notify_order_status_change(order, prev_status=prev_status)
    except Exception:
        logger.exception("No pude postear el cambio de estado en Discord")

    embed = {
        "title": f"{label} · `#{order.display_number}`",
        "description": f"Estado anterior: `{prev_status}` → ahora: `{new_status}`",
        "color": color,
    }
    return _ephemeral(embeds=[embed])


def _handle_component(payload: dict) -> dict[str, Any]:
    """Procesa un click de botón (MESSAGE_COMPONENT)."""
    data = payload.get("data", {}) or {}
    custom_id = str(data.get("custom_id", ""))
    user_id = _user_id_from_payload(payload)

    parts = custom_id.split(":")
    if len(parts) >= 3 and parts[0] == "order":
        action = parts[1]
        try:
            order_pk = int(parts[2])
        except ValueError:
            return _ephemeral(f"PK de pedido inválido en `{custom_id}`.")
        return _do_order_action(action, order_pk, user_id)

    return _ephemeral(f"Botón sin handler: `{custom_id}`.")


# ---------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------

def handle_interaction(payload: dict) -> dict[str, Any]:
    """Procesa una interacción ya verificada y devuelve la respuesta JSON."""
    itype = payload.get("type")

    if itype == INTERACTION_PING:
        return {"type": RESPONSE_PONG}

    if itype == INTERACTION_APPLICATION_COMMAND:
        data = payload.get("data", {}) or {}
        name = data.get("name", "")
        handler = _DISPATCHER.get(name)
        if not handler:
            return _ephemeral(f"Comando `/{name}` no implementado.")
        try:
            return handler(data)
        except Exception:
            logger.exception("Error ejecutando /%s", name)
            return _ephemeral("Ocurrió un error procesando el comando. Mirá los logs.")

    if itype == INTERACTION_MESSAGE_COMPONENT:
        try:
            return _handle_component(payload)
        except Exception:
            logger.exception("Error procesando botón")
            return _ephemeral("Ocurrió un error procesando el botón. Mirá los logs.")
    return _ephemeral("Tipo de interacción no soportado todavía.")


def verify_signature(body: bytes, signature_hex: str, timestamp: str,
                     public_key_hex: str) -> bool:
    """Verifica la firma Ed25519 que Discord envía en cada request."""
    if not (signature_hex and timestamp and public_key_hex):
        return False
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature_hex))
        return True
    except BadSignatureError:
        return False
    except Exception:
        logger.exception("Error verificando firma Discord")
        return False
