"""Helpers de alto nivel para mandar avisos al back-office en Discord.

Cada función está pensada para reemplazar 1:1 una notificación que hoy va
a Telegram (al canal de distribuidores o al DM admin). Si el bot no está
configurado, devuelven ``None`` sin romper nada.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.urls import reverse

from . import client

logger = logging.getLogger(__name__)


# ---------- Helpers internos ----------

def _admin_url(request, view_name: str, *args) -> str:
    """Construye un URL absoluto al admin (para botones ``Ver en admin``)."""
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


# ---------- API pública ----------

def notify_test(channel_key: str = "admin", message: str = "🔔 Test de conexión Discord ✓") -> dict | None:
    """Manda un mensaje de prueba al canal indicado."""
    if not client.is_configured():
        return None
    cid = _channel(channel_key)
    if not cid:
        return None
    return client.send_message(cid, message)


def notify_new_code_request(request, code_request) -> dict | None:
    """Aviso de nuevo pedido de código (del verificador `/codigos/`).

    Reemplaza el `notify_admin()` de Telegram que se usa hoy en
    ``support.views._notify_admins_new_code_request``.
    """
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
        color=0xF59E0B,  # ámbar (acción requerida)
        components=components,
        footer="Verificador de códigos · Jheliz",
    )
