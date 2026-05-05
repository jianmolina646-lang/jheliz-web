"""Middleware que restringe el acceso al admin a una lista de IPs permitidas.

Activación: la variable de entorno ``ADMIN_IP_ALLOWLIST`` con un valor
separado por comas que puede contener IPs simples (``203.0.113.42``) o
rangos en notación CIDR (``203.0.113.0/24``, ``2001:db8::/32``). Si la
variable está vacía o no existe, el middleware es **no-op** (sin
bloqueos), de modo que no rompe nada en CI ni en setups donde el
allowlist no aplica (ej. red móvil con IP variable).

Modos:

- **Hard (default)**: cualquier request a ``/jheliz-admin/*`` desde una
  IP fuera del allowlist responde 403.
- **Soft (``ADMIN_IP_ALLOWLIST_SOFT=True``)**: deja pasar pero loguea
  un WARNING y dispara una alerta a Telegram (si está configurado).
  Útil para validar antes de activar el modo hard sin riesgo.

La IP del cliente se calcula respetando ``X-Forwarded-For`` (porque la
app está detrás de nginx). Solo se confía en el primer salto del header,
que en el deploy real lo escribe nginx — cualquier valor que el cliente
intente inyectar más allá se ignora.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Iterable

from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)

_ADMIN_PREFIX = "/jheliz-admin/"


def _parse_networks(raw: str) -> list[ipaddress._BaseNetwork]:
    """Convierte ``"a,b,c"`` en una lista de redes ipaddress.

    Acepta IPs simples y CIDRs. Ítems vacíos o inválidos se descartan
    con un log de warning (no se rompe el middleware por una entrada
    mala — preferible que pase a permitir todo, ya que falla cerrado
    cuando la lista efectiva queda vacía).
    """
    nets: list[ipaddress._BaseNetwork] = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("ADMIN_IP_ALLOWLIST: entrada inválida %r — ignorada", item)
    return nets


def _client_ip(request) -> str:
    """IP del cliente respetando X-Forwarded-For del proxy nginx."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # En el deploy real, nginx pone aquí: "<ip-real>, <ips-intermedios>".
        # Tomamos solo la primera entrada — el resto puede ser inyectado
        # por el cliente y no es confiable.
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _ip_allowed(ip_str: str, networks: Iterable[ipaddress._BaseNetwork]) -> bool:
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def _alert_admin(message: str) -> None:
    """Dispara una alerta a Telegram (best-effort, no rompe el request)."""
    try:
        from orders.telegram import notify_admin
        notify_admin(message)
    except Exception:  # pragma: no cover - infra; no debe romper el middleware
        logger.exception("No se pudo notificar al admin sobre allowlist")


class AdminIPAllowlistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Cache estática al levantar el proceso. Si se cambian las env
        # vars hay que reiniciar gunicorn, igual que cualquier otra
        # config — los settings se evalúan en import time.
        raw = getattr(settings, "ADMIN_IP_ALLOWLIST", "") or ""
        self.networks = _parse_networks(raw)
        self.soft_mode = bool(getattr(settings, "ADMIN_IP_ALLOWLIST_SOFT", False))
        self.enabled = bool(self.networks)
        if self.enabled:
            logger.info(
                "AdminIPAllowlist activado (%d redes, soft=%s)",
                len(self.networks),
                self.soft_mode,
            )

    def __call__(self, request):
        if self.enabled and request.path.startswith(_ADMIN_PREFIX):
            ip = _client_ip(request)
            if not _ip_allowed(ip, self.networks):
                ua = request.META.get("HTTP_USER_AGENT", "")[:200]
                if self.soft_mode:
                    logger.warning(
                        "AdminIPAllowlist (soft): acceso al admin desde IP fuera del allowlist "
                        "ip=%s path=%s ua=%s",
                        ip, request.path, ua,
                    )
                    _alert_admin(
                        "⚠️ <b>Admin: IP fuera del allowlist (soft mode)</b>\n"
                        f"IP: <code>{ip or '?'}</code>\n"
                        f"Path: {request.path}\n"
                        f"User-Agent: <code>{ua}</code>"
                    )
                else:
                    logger.warning(
                        "AdminIPAllowlist: bloqueado acceso al admin "
                        "ip=%s path=%s ua=%s",
                        ip, request.path, ua,
                    )
                    _alert_admin(
                        "🚫 <b>Admin: bloqueado intento desde IP no autorizada</b>\n"
                        f"IP: <code>{ip or '?'}</code>\n"
                        f"Path: {request.path}\n"
                        f"User-Agent: <code>{ua}</code>"
                    )
                    return HttpResponseForbidden(
                        "Acceso restringido. Tu IP no está autorizada para usar el admin."
                    )
        return self.get_response(request)
