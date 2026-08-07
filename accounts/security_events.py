"""Creación y alerta de eventos de seguridad de alto valor."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache

from config.client_ip import get_client_ip
from config.request_context import current_request_context

logger = logging.getLogger("security.events")


def record_security_event(
    event_type: str,
    *,
    severity: str = "warning",
    request=None,
    actor=None,
    username: str = "",
    metadata: dict | None = None,
    alert: bool = False,
):
    """Persiste un evento sanitizado. Nunca pasar secretos dentro de metadata."""
    from .models import SecurityEvent, User

    ctx = current_request_context()
    actor_id = getattr(actor, "pk", None) or ctx.user_id
    try:
        event = SecurityEvent.objects.create(
            event_type=event_type[:80],
            severity=severity,
            actor_id=actor_id if actor_id and User.objects.filter(pk=actor_id).exists() else None,
            username=(username or getattr(actor, "get_username", lambda: "")())[:254],
            ip_address=get_client_ip(request) if request is not None else ctx.ip_address,
            user_agent=((request.META.get("HTTP_USER_AGENT") or "") if request is not None else ctx.user_agent)[:300],
            path=((request.path or "") if request is not None else ctx.path)[:500],
            request_id=((request.headers.get("X-Request-ID") or "") if request is not None else ctx.request_id)[:100],
            metadata=metadata or {},
        )
    except Exception:
        # La instrumentación nunca debe tumbar un login/webhook durante una
        # migración o una indisponibilidad temporal de la tabla de eventos.
        logger.exception("No se pudo persistir security_event type=%s", event_type)
        return None
    logger.warning("security_event type=%s severity=%s id=%s ip=%s", event_type, severity, event.pk, event.ip_address)
    if alert or severity == SecurityEvent.Severity.CRITICAL:
        _send_alert(event)
    return event


def _send_alert(event) -> None:
    if not getattr(settings, "SECURITY_EVENT_ALERTS", True):
        return
    # Evita que un atacante convierta un endpoint público en una bomba de
    # correo/Telegram. Todos los intentos se guardan; la alerta se agrupa 5 min.
    alert_key = f"security-alert:{event.event_type}:{event.ip_address or 'unknown'}"
    if not cache.add(alert_key, 1, timeout=300):
        return
    recipient = getattr(settings, "SUPPORT_ADMIN_EMAIL", "")
    if recipient:
        send_mail(
            f"[Seguridad] {event.event_type}",
            f"Evento: {event.event_type}\nSeveridad: {event.severity}\nUsuario: {event.username or '-'}\nIP: {event.ip_address or '-'}\nRuta: {event.path or '-'}\nID: {event.pk}",
            getattr(settings, "DEFAULT_FROM_EMAIL", recipient),
            [recipient],
            fail_silently=True,
        )
    try:
        from orders.telegram import _admin_chat_id, is_configured, send_message
        if is_configured() and _admin_chat_id():
            send_message(
                _admin_chat_id(),
                f"🚨 <b>Evento de seguridad</b>\nTipo: <code>{event.event_type}</code>\nUsuario: <code>{event.username or '-'}</code>\nIP: <code>{event.ip_address or '-'}</code>\nID: {event.pk}",
            )
    except Exception:
        logger.exception("No se pudo enviar alerta de seguridad por Telegram")
