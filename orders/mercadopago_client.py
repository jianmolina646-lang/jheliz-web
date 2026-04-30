"""Cliente wrapper para Mercado Pago."""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse

try:
    import mercadopago  # type: ignore
except ImportError:  # pragma: no cover
    mercadopago = None

if TYPE_CHECKING:
    from .models import Order

logger = logging.getLogger(__name__)


class MercadoPagoError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.MERCADOPAGO_ACCESS_TOKEN)


# ---------------------------------------------------------------------------
# Verificación de firma de webhook
#
# Mercado Pago firma cada notificación con HMAC-SHA256 usando un secreto que
# se configura en el panel de Webhooks. Manda dos headers:
#
#   x-signature: ts=<unix-ts>,v1=<hex-digest>
#   x-request-id: <uuid>
#
# El manifest a firmar es:
#   id:<data.id de la query string>;request-id:<x-request-id>;ts:<ts>;
#
# Doc:
#   https://www.mercadopago.com.pe/developers/es/docs/your-integrations/notifications/webhooks
# ---------------------------------------------------------------------------


def _parse_signature_header(header: str) -> tuple[str, str]:
    """Devuelve (ts, v1) parseando el header ``x-signature``.

    Formato: ``ts=1704908010,v1=618c8534...``. Las partes pueden venir en
    cualquier orden y rodeadas de espacios.
    """
    ts = ""
    v1 = ""
    for part in header.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "ts":
            ts = v
        elif k == "v1":
            v1 = v
    return ts, v1


def verify_webhook_signature(
    *,
    signature_header: str,
    request_id: str,
    data_id: str,
    secret: str,
) -> bool:
    """Verifica la firma HMAC del webhook de Mercado Pago.

    Devuelve True solo si el header está bien formado y el HMAC computado
    sobre el manifest oficial coincide con el valor ``v1`` recibido.
    Comparación constant-time vía :func:`hmac.compare_digest`.
    """
    if not (secret and signature_header and request_id and data_id):
        return False
    ts, received_hex = _parse_signature_header(signature_header)
    if not (ts and received_hex):
        return False
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    expected_hex = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hex, received_hex)


def _sdk():
    if mercadopago is None:
        raise MercadoPagoError("El SDK 'mercadopago' no est\u00e1 instalado.")
    if not is_configured():
        raise MercadoPagoError(
            "Mercado Pago no est\u00e1 configurado. Define MERCADOPAGO_ACCESS_TOKEN en .env."
        )
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def _absolute(request, url_name: str, *args) -> str:
    path = reverse(url_name, args=args)
    return request.build_absolute_uri(path)


def create_preference(request, order: "Order") -> dict:
    """Crea una preferencia de checkout pro y devuelve el dict con init_point y id."""
    sdk = _sdk()

    items_payload = []
    for item in order.items.select_related("product", "plan"):
        unit_price = float(item.unit_price.quantize(Decimal("0.01")))
        description_bits = [item.plan_name]
        if item.requested_profile_name:
            description_bits.append(f"Perfil: {item.requested_profile_name}")
        if item.requested_pin:
            description_bits.append(f"PIN: {item.requested_pin}")
        items_payload.append({
            "id": str(item.plan_id),
            "title": item.product_name,
            "description": " \u2014 ".join(description_bits),
            "quantity": int(item.quantity),
            "unit_price": unit_price,
            "currency_id": order.currency or "PEN",
        })

    success_url = _absolute(request, "orders:checkout_return", order.uuid)
    webhook_url = _absolute(request, "orders:mercadopago_webhook")

    # Mercado Pago rechaza back_urls/notification_url localhost y pide HTTPS.
    # En local, saltamos esos campos; en prod/tunnel usamos los reales.
    def _is_public(url: str) -> bool:
        return url.startswith("https://") and "127.0.0.1" not in url and "localhost" not in url

    preference_data = {
        "items": items_payload,
        "external_reference": str(order.uuid),
        "metadata": {
            "order_id": order.pk,
            "order_uuid": str(order.uuid),
        },
    }
    if order.email:
        preference_data["payer"] = {"email": order.email}

    if _is_public(success_url):
        preference_data["back_urls"] = {
            "success": success_url,
            "pending": success_url,
            "failure": success_url,
        }
        preference_data["auto_return"] = "approved"

    if _is_public(webhook_url):
        preference_data["notification_url"] = webhook_url

    result = sdk.preference().create(preference_data)
    response = result.get("response", {})
    if result.get("status", 500) >= 400:
        logger.error("Mercado Pago preference error: %s", response)
        raise MercadoPagoError(response.get("message", "Error al crear la preferencia."))

    return response


def fetch_payment(payment_id: str) -> dict:
    sdk = _sdk()
    result = sdk.payment().get(payment_id)
    response = result.get("response", {})
    if result.get("status", 500) >= 400:
        logger.error("Mercado Pago payment fetch error: %s", response)
        raise MercadoPagoError(response.get("message", "No se pudo consultar el pago."))
    return response
