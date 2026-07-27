"""Integracion multi-inquilino con Meta WhatsApp Cloud API."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from datetime import timedelta
from urllib import error, parse, request

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Subscription, WhatsAppConnection, WhatsAppReminderDelivery

logger = logging.getLogger(__name__)


class MetaAPIError(RuntimeError):
    pass


def _graph(path: str) -> str:
    version = getattr(settings, "META_GRAPH_API_VERSION", "v23.0")
    return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"


def _call(path, *, token="", method="GET", data=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = request.Request(_graph(path), data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise MetaAPIError(f"Meta API {exc.code}: {detail}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise MetaAPIError(f"No se pudo conectar con Meta: {exc}") from exc


def exchange_code(code: str) -> str:
    query = parse.urlencode({
        "client_id": settings.META_APP_ID,
        "client_secret": settings.META_APP_SECRET,
        "code": code,
    })
    data = _call(f"oauth/access_token?{query}")
    token = data.get("access_token", "")
    if not token:
        raise MetaAPIError("Meta no devolvio un token de acceso.")
    return token


def finish_signup(owner, *, code, waba_id, phone_number_id):
    token = exchange_code(code)
    _call(f"{waba_id}/subscribed_apps", token=token, method="POST", data={})
    phone = _call(
        f"{phone_number_id}?fields=display_phone_number,verified_name",
        token=token,
    )
    connection, _ = WhatsAppConnection.objects.update_or_create(
        owner=owner,
        defaults={
            "access_token": token,
            "waba_id": str(waba_id),
            "phone_number_id": str(phone_number_id),
            "display_phone_number": phone.get("display_phone_number", ""),
            "verified_name": phone.get("verified_name", ""),
            "status": WhatsAppConnection.Status.ACTIVE,
            "is_enabled": True,
            "last_error": "",
            "connected_at": timezone.now(),
        },
    )
    return connection


def send_template(connection, recipient, parameters):
    payload = {
        "messaging_product": "whatsapp",
        "to": re.sub(r"\D", "", recipient),
        "type": "template",
        "template": {
            "name": connection.template_name,
            "language": {"code": connection.template_language},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(value)} for value in parameters],
            }],
        },
    }
    data = _call(
        f"{connection.phone_number_id}/messages",
        token=connection.access_token,
        method="POST",
        data=payload,
    )
    messages = data.get("messages") or []
    if not messages or not messages[0].get("id"):
        raise MetaAPIError("Meta acepto la solicitud sin devolver ID de mensaje.")
    return messages[0]["id"]


def _masked_email(value):
    value = (value or "").strip()
    if "@" not in value:
        return value[:3] + "***"
    local, domain = value.split("@", 1)
    return f"{local[:3]}***@{domain}"


def send_due_reminders(today=None):
    """Envia cada recordatorio una sola vez por ciclo de vencimiento."""
    today = today or timezone.localdate()
    sent = 0
    connections = WhatsAppConnection.objects.filter(
        status=WhatsAppConnection.Status.ACTIVE, is_enabled=True,
    ).select_related("owner", "owner__jc_tenant")
    for connection in connections:
        for days in connection.windows():
            target = today + timedelta(days=days)
            subscriptions = Subscription.objects.filter(
                owner=connection.owner, is_archived=False,
                expires_at__date=target,
                client__whatsapp_opt_in_at__isnull=False,
            ).exclude(client__whatsapp="").select_related("client", "service")
            for sub in subscriptions:
                try:
                    with transaction.atomic():
                        delivery, created = WhatsAppReminderDelivery.objects.get_or_create(
                            subscription=sub,
                            expiry_date=target,
                            reminder_days=days,
                            defaults={
                                "owner": connection.owner,
                                "recipient": sub.client.whatsapp_digits,
                                "template_name": connection.template_name,
                            },
                        )
                        if not created and delivery.status != WhatsAppReminderDelivery.Status.FAILED:
                            continue
                        if delivery.attempts >= 3:
                            continue
                        delivery.attempts += 1
                        delivery.save(update_fields=["attempts", "updated_at"])
                    tenant = getattr(connection.owner, "jc_tenant", None)
                    business = getattr(tenant, "business_name", "") or connection.owner.username
                    message_id = send_template(connection, sub.client.whatsapp_digits, [
                        sub.client.name,
                        sub.service.name,
                        _masked_email(sub.account_email),
                        timezone.localtime(sub.expires_at).strftime("%d/%m/%Y"),
                        business,
                    ])
                    delivery.meta_message_id = message_id
                    delivery.status = WhatsAppReminderDelivery.Status.SENT
                    delivery.sent_at = timezone.now()
                    delivery.last_error = ""
                    delivery.save()
                    sent += 1
                except (MetaAPIError, IntegrityError) as exc:
                    logger.exception("Fallo recordatorio WhatsApp subscription=%s", sub.pk)
                    if "delivery" in locals():
                        delivery.status = WhatsAppReminderDelivery.Status.FAILED
                        delivery.last_error = str(exc)[:1000]
                        delivery.save()
    return sent


def verify_signature(raw_body: bytes, signature: str) -> bool:
    secret = getattr(settings, "META_APP_SECRET", "")
    if not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


def process_webhook(payload):
    updated = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            statuses = (change.get("value") or {}).get("statuses") or []
            for item in statuses:
                message_id = item.get("id", "")
                state = item.get("status", "")
                mapping = {
                    "sent": WhatsAppReminderDelivery.Status.SENT,
                    "delivered": WhatsAppReminderDelivery.Status.DELIVERED,
                    "read": WhatsAppReminderDelivery.Status.READ,
                    "failed": WhatsAppReminderDelivery.Status.FAILED,
                }
                if message_id and state in mapping:
                    fields = {"status": mapping[state]}
                    now = timezone.now()
                    if state == "delivered":
                        fields["delivered_at"] = now
                    elif state == "read":
                        fields["read_at"] = now
                    elif state == "failed":
                        errors = item.get("errors") or []
                        fields["last_error"] = json.dumps(errors, ensure_ascii=False)[:1000]
                    updated += WhatsAppReminderDelivery.objects.filter(
                        meta_message_id=message_id,
                    ).update(**fields)
    return updated
