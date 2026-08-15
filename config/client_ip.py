"""Obtención segura de la IP del cliente detrás de proxies conocidos."""

from __future__ import annotations

import ipaddress

from django.conf import settings


def _is_trusted_proxy(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    for network in getattr(settings, "TRUSTED_PROXY_NETWORKS", ()):
        try:
            if address in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request) -> str | None:
    """Devuelve una IP validada; sólo confía en headers desde un proxy permitido."""
    if request is None:
        return None
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    candidate = remote
    if _is_trusted_proxy(remote):
        # Nginx sobrescribe X-Real-IP; no aceptamos cadenas XFF aportadas por clientes.
        candidate = (request.META.get("HTTP_X_REAL_IP") or remote).strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def axes_client_ip(request):
    """Callable compatible con AXES_CLIENT_IP_CALLABLE."""
    return get_client_ip(request)
