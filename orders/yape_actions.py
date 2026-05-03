"""Acciones core de Yape (confirmar / rechazar) reutilizables.

Se llaman desde el admin web y desde el callback del bot de Telegram.
Devuelven un ``YapeActionResult`` con ``ok`` y ``message`` para que el
caller decida cómo presentarlo al usuario (mensaje admin, toast Telegram).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from . import emails
from .models import Order


@dataclass
class YapeActionResult:
    ok: bool
    message: str


def confirm_yape_payment(order: Order) -> YapeActionResult:
    if order.payment_provider != "yape" or not order.payment_proof:
        return YapeActionResult(False, "Este pedido no tiene comprobante Yape.")
    from .auto_delivery import auto_deliver_distributor_order

    now = timezone.now()
    delivered, missing = auto_deliver_distributor_order(order, paid_at=now)
    if delivered:
        return YapeActionResult(
            True,
            f"Pago confirmado y cuenta entregada al distribuidor de #{order.short_uuid}.",
        )

    order.status = Order.Status.PREPARING
    order.paid_at = order.paid_at or now
    order.payment_rejection_reason = ""
    order.save(update_fields=["status", "paid_at", "payment_rejection_reason"])
    if missing:
        return YapeActionResult(
            True,
            f"Pago confirmado para #{order.short_uuid}. Falta stock para: {', '.join(missing)}.",
        )
    return YapeActionResult(
        True,
        f"Pago confirmado para #{order.short_uuid}. Cliente notificado.",
    )


def reject_yape_payment(order: Order, reason: str) -> YapeActionResult:
    if order.payment_provider != "yape":
        return YapeActionResult(False, "Este pedido no es Yape.")
    reason = (reason or "").strip()
    if not reason:
        reason = (
            "No pudimos verificar el comprobante. Por favor sube una captura "
            "más clara donde se vea el monto y el destinatario."
        )
    order.status = Order.Status.PENDING
    order.payment_rejection_reason = reason
    order.save(update_fields=["status", "payment_rejection_reason"])
    try:
        emails.send_yape_proof_rejected(order)
    except Exception:
        pass
    return YapeActionResult(
        True,
        f"Comprobante rechazado para #{order.short_uuid}. Motivo enviado al cliente.",
    )
