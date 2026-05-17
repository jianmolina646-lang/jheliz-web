"""Dispatcher de slash commands de Discord.

Discord postea un JSON a nuestro webhook (`/discord/interactions/`) cuando
alguien usa un slash command o aprieta un botón. La firma se verifica con
la PUBLIC KEY del bot (Ed25519). Esta verificación es obligatoria para
que Discord considere el endpoint válido.

Comandos implementados:

- ``/buscar <consulta>`` — busca pedidos por email / número JH-XXXX.
- ``/pendientes`` — lista los últimos 10 pedidos esperando acción.
- ``/entregar <numero>`` — abre el formulario de entrega del admin.
- ``/stock <producto>`` — muestra stock disponible de un plan.

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


_DISPATCHER = {
    "buscar": _cmd_buscar,
    "pendientes": _cmd_pendientes,
    "entregar": _cmd_entregar,
    "stock": _cmd_stock,
}


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

    # Botones / modales podrían venir aquí en el futuro.
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
