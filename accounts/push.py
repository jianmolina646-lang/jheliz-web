"""Helpers para enviar notificaciones Web Push.

Usa pywebpush + py-vapid para empaquetar y firmar el payload con las claves
VAPID configuradas en settings. Si las claves no están seteadas, las funciones
hacen un no-op silencioso (útil en dev).
"""

from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _vapid_configured() -> bool:
    return bool(
        getattr(settings, "VAPID_PUBLIC_KEY", "")
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
    )


def send_to_subscription(sub, *, title: str, body: str, url: str = "/", icon: str = "") -> bool:
    """Envía una notificación a una sola subscripción. Devuelve True si fue OK.

    Si la subscripción ya no es válida (HTTP 404/410), la marca inactiva.
    """
    if not _vapid_configured():
        logger.warning("VAPID no configurado — no se envió la notificación push.")
        return False

    from pywebpush import WebPushException, webpush

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": icon or "/static/img/icon-192.png",
    })

    sub_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    try:
        webpush(
            subscription_info=sub_info,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CLAIM_EMAIL},
            ttl=60 * 60 * 24,  # 1 día
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        sub.last_error = f"WebPush {status or ''}: {exc}"[:200]
        sub.failed_count += 1
        # 404 / 410: subscripción muerta, dar de baja
        if status in (404, 410):
            sub.is_enabled = False
        elif sub.failed_count >= 3:
            sub.is_enabled = False
        sub.save(update_fields=["last_error", "failed_count", "is_enabled"])
        return False
    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Error inesperado enviando push: %s", exc)
        sub.last_error = f"Error: {exc}"[:200]
        sub.failed_count += 1
        sub.save(update_fields=["last_error", "failed_count"])
        return False

    sub.last_used_at = timezone.now()
    sub.failed_count = 0
    sub.last_error = ""
    sub.save(update_fields=["last_used_at", "failed_count", "last_error"])
    return True


def broadcast(
    subs: Iterable,
    *,
    title: str,
    body: str,
    url: str = "/",
    icon: str = "",
) -> tuple[int, int]:
    """Envía a una lista de subscripciones. Devuelve (sent, failed)."""
    sent = failed = 0
    for sub in subs:
        if not sub.is_enabled:
            continue
        ok = send_to_subscription(sub, title=title, body=body, url=url, icon=icon)
        if ok:
            sent += 1
        else:
            failed += 1
    return sent, failed
