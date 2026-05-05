"""Alertas de seguridad al admin via Telegram.

Hooks principales:

- ``django_axes.user_locked_out`` → cuenta bloqueada por intentos fallidos.
- ``django.contrib.auth.signals.user_login_failed`` → primer intento
  fallido en ventana corta (rate-limited a 1 alerta cada 15 min por IP
  para no inundar Telegram).
- Helper genérico ``alert_admin_security(event, **fields)`` para usar
  desde cualquier lugar del código (ej. webhook MP con firma inválida).

Todo es **best-effort**: si Telegram no está configurado o falla, se
loguea pero NO se levanta excepción — la seguridad nunca puede romper
el flujo principal del sitio.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Cache simple en memoria para rate-limit por IP/evento (no persistente
# pero suficiente: si se reinicia gunicorn se pierde, en el peor caso
# llegan 1-2 alertas extra).
_LAST_ALERT_TS: dict[str, float] = {}
_RATE_WINDOW_SECONDS = 15 * 60  # 15 min


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    last = _LAST_ALERT_TS.get(key, 0.0)
    if now - last < _RATE_WINDOW_SECONDS:
        return True
    _LAST_ALERT_TS[key] = now
    return False


def _send(message: str) -> None:
    try:
        from orders.telegram import notify_admin
        notify_admin(message)
    except Exception:  # pragma: no cover - infra
        logger.exception("Fallo enviando alerta de seguridad a Telegram")


def alert_admin_security(event: str, /, **fields: Any) -> None:
    """Envía una alerta arbitraria al admin.

    Args:
        event: título del evento (ej. ``"webhook MP firma inválida"``).
        **fields: pares clave-valor que se renderizan como ``key: value``
            en líneas separadas.
    """
    lines = [f"🔐 <b>{event}</b>"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        # Truncar valores largos para no romper el límite de 4096 chars
        # de Telegram.
        text = str(value)
        if len(text) > 300:
            text = text[:299] + "…"
        lines.append(f"<b>{key}:</b> <code>{text}</code>")
    _send("\n".join(lines))


def _connect_signals() -> None:
    """Conecta los handlers a sus signals. Se invoca desde AppConfig.ready."""

    # 1) django-axes: cuenta bloqueada por límite de intentos. Esto es la
    # señal MÁS importante — significa que alguien está probando contraseñas.
    try:
        from axes.signals import user_locked_out

        @receiver(user_locked_out, dispatch_uid="security_alerts.user_locked_out")
        def _on_lockout(*, request=None, username=None, ip_address=None, **kwargs):
            key = f"lockout:{ip_address or '?'}"
            if _rate_limited(key):
                return
            ua = ""
            path = ""
            if request is not None:
                ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:200]
                path = request.path
            alert_admin_security(
                "Cuenta bloqueada por intentos fallidos",
                Usuario=username or "?",
                IP=ip_address or "?",
                Path=path,
                UA=ua,
            )
    except ImportError:  # pragma: no cover - axes siempre instalado en este repo
        logger.warning("django-axes no instalado — no se conectarán alertas de lockout")

    # 2) Login fallido (cualquier intento, no solo el que dispara lockout).
    # Se rate-limita a 1 cada 15 min por IP+username para no inundar.
    try:
        from django.contrib.auth.signals import user_login_failed

        @receiver(user_login_failed, dispatch_uid="security_alerts.user_login_failed")
        def _on_login_failed(*, credentials=None, request=None, **kwargs):
            if request is None:
                return
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            ip = ip or request.META.get("REMOTE_ADDR", "") or "?"
            username = (credentials or {}).get("username") or "?"
            # Solo notificamos si el path es del admin — los logins fallidos
            # del frontend (clientes) no son interesantes y serían demasiados.
            if not request.path.startswith("/jheliz-admin/"):
                return
            key = f"login_failed:{ip}:{username}"
            if _rate_limited(key):
                return
            alert_admin_security(
                "Intento de login fallido en admin",
                Usuario=username,
                IP=ip,
                Path=request.path,
            )
    except ImportError:  # pragma: no cover
        pass
