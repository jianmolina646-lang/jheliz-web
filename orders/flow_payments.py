"""Flow QR para pedidos mayoristas."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from gestion.flow_payments import FlowError, _request
from .models import Order


def configured():
    from django.conf import settings
    return bool(settings.FLOW_API_KEY and settings.FLOW_SECRET_KEY and settings.FLOW_PAYMENT_METHOD)


def create_payment(*, order, email, confirmation_url, return_url):
    import json
    from django.conf import settings
    return _request("payment/create", {
        "commerceOrder": f"JHO-{order.pk}-{order.uuid.hex[:8]}",
        "subject": "Cuenta completa Jheliz Distribuidores",
        "currency": "PEN",
        "amount": f"{Decimal(order.total):.2f}",
        "email": email,
        "paymentMethod": settings.FLOW_PAYMENT_METHOD,
        "urlConfirmation": confirmation_url,
        "urlReturn": return_url,
        "optional": json.dumps({"order_id": order.pk}, separators=(",", ":")),
        "timeout": settings.FLOW_PAYMENT_TIMEOUT,
    }, "POST")


def get_status(token):
    return _request("payment/getStatus", {"token": token})


@transaction.atomic
def apply_paid_status(*, token, payload):
    order = Order.objects.select_for_update().select_related("user").filter(flow_token=token).first()
    if order is None:
        raise ValidationError("La orden Flow no pertenece a este comercio.")
    received = Decimal(str(payload.get("amount"))).quantize(Decimal("0.01"))
    if str(payload.get("commerceOrder")) != f"JHO-{order.pk}-{order.uuid.hex[:8]}" or received != Decimal(order.total).quantize(Decimal("0.01")):
        raise ValidationError("Los datos de la orden Flow no coinciden.")
    order.payment_reference = str(payload.get("flowOrder") or order.flow_order or "")
    order.flow_order = payload.get("flowOrder") or order.flow_order
    if int(payload.get("status", 0)) != 2:
        order.save(update_fields=["payment_reference", "flow_order"])
        return order, False
    if order.status == Order.Status.DELIVERED:
        return order, False
    order.save(update_fields=["payment_reference", "flow_order"])
    from .auto_delivery import auto_deliver_distributor_order
    delivered, _missing = auto_deliver_distributor_order(order, paid_at=timezone.now())
    if not delivered and order.status == Order.Status.PENDING:
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])
    return order, delivered
