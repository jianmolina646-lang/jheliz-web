"""Integracion server-to-server con Flow Peru."""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Tenant, TenantPayment


class FlowError(Exception):
    pass


def configured():
    return bool(settings.FLOW_API_KEY and settings.FLOW_SECRET_KEY and settings.FLOW_PAYMENT_METHOD)


def _signed(params):
    values = {key: str(value) for key, value in params.items() if value not in (None, "")}
    raw = "".join(key + values[key] for key in sorted(values))
    values["s"] = hmac.new(settings.FLOW_SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return values


def _request(path, params, method="GET"):
    if not settings.FLOW_API_KEY or not settings.FLOW_SECRET_KEY:
        raise ImproperlyConfigured("Flow no esta configurado.")
    signed = _signed({"apiKey": settings.FLOW_API_KEY, **params})
    encoded = urlencode(signed).encode()
    url = f"{settings.FLOW_API_URL}/{path.lstrip('/')}"
    request = Request(url if method == "POST" else f"{url}?{encoded.decode()}", data=encoded if method == "POST" else None, method=method)
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=settings.FLOW_HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise FlowError("Flow no pudo procesar la solicitud.") from exc


def create_payment(*, payment, email, confirmation_url, return_url):
    params = {
        "commerceOrder": payment.provider_order_id,
        "subject": "Renovacion mensual Jheliz Control",
        "currency": "PEN",
        "amount": f"{payment.amount:.2f}",
        "email": email,
        "paymentMethod": settings.FLOW_PAYMENT_METHOD,
        "urlConfirmation": confirmation_url,
        "urlReturn": return_url,
        "optional": json.dumps({"payment_id": payment.pk}, separators=(",", ":")),
        "timeout": settings.FLOW_PAYMENT_TIMEOUT,
    }
    return _request("payment/create", params, "POST")


def get_status(token):
    return _request("payment/getStatus", {"token": token})


@transaction.atomic
def apply_paid_status(*, token, payload):
    payment = TenantPayment.objects.select_for_update().filter(provider_token=token).first()
    if payment is None:
        raise ValidationError("La orden de Flow no pertenece a este comercio.")
    expected = Decimal(payment.amount).quantize(Decimal("0.01"))
    received = Decimal(str(payload.get("amount"))).quantize(Decimal("0.01"))
    if str(payload.get("commerceOrder")) != payment.provider_order_id or received != expected:
        raise ValidationError("Los datos de la orden de Flow no coinciden.")
    payment.provider_payload = payload
    payment.provider_flow_order = payload.get("flowOrder") or payment.provider_flow_order
    if int(payload.get("status", 0)) != 2:
        payment.save(update_fields=["provider_payload", "provider_flow_order"])
        return payment, False
    if payment.status == TenantPayment.Status.APPROVED:
        return payment, False
    tenant = Tenant.objects.select_for_update().get(pk=payment.tenant_id)
    payment.status = TenantPayment.Status.APPROVED
    payment.reviewed_at = payment.verified_at = timezone.now()
    payment.save(update_fields=["status", "reviewed_at", "verified_at", "provider_payload", "provider_flow_order"])
    tenant.extend(payment.days or 30)
    return payment, True
