"""Cliente wrapper para Mercado Pago."""

from __future__ import annotations

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
