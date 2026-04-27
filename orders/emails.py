"""Correos transaccionales."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse


def _order_absolute_url(order) -> str:
    return f"{settings.SITE_URL}{reverse('orders:detail', args=[order.uuid])}"


def _send(order, subject: str, template: str) -> None:
    if not order.email:
        return
    context = {
        "order": order,
        "items": list(order.items.all()),
        "order_url": _order_absolute_url(order),
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "CURRENCY_SYMBOL": settings.DEFAULT_CURRENCY_SYMBOL,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
    }
    body = render_to_string(template, context)
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    message.content_subtype = "html"
    message.send(fail_silently=True)


def send_order_received(order) -> None:
    _send(order, f"Recibimos tu pedido #{order.short_uuid} \u2014 {settings.SITE_NAME}",
          "emails/order_received.html")


def send_order_preparing(order) -> None:
    _send(order, f"Estamos preparando tu pedido #{order.short_uuid}",
          "emails/order_preparing.html")


def send_order_delivered(order) -> None:
    _send(order, f"Tu pedido #{order.short_uuid} est\u00e1 listo",
          "emails/order_delivered.html")


def send_yape_proof_received(order) -> None:
    _send(order, f"Recibimos tu comprobante Yape \u2014 pedido #{order.short_uuid}",
          "emails/order_yape_received.html")


def send_yape_proof_rejected(order) -> None:
    _send(order, f"Necesitamos otro comprobante \u2014 pedido #{order.short_uuid}",
          "emails/order_yape_rejected.html")


def send_expiry_reminder(order, items, days_left: int) -> None:
    """Recordatorio de renovaci\u00f3n N d\u00edas antes del vencimiento.

    ``items`` es una lista de ``OrderItem`` que vencen en ``days_left`` d\u00edas.
    """
    if not order.email or not items:
        return
    context = {
        "order": order,
        "items": list(items),
        "days_left": days_left,
        "order_url": _order_absolute_url(order),
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "CURRENCY_SYMBOL": settings.DEFAULT_CURRENCY_SYMBOL,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
    }
    body = render_to_string("emails/order_expiring.html", context)
    if days_left <= 1:
        subject = f"Tu suscripci\u00f3n vence ma\u00f1ana \u2014 #{order.short_uuid}"
    else:
        subject = f"Tu suscripci\u00f3n vence en {days_left} d\u00edas \u2014 #{order.short_uuid}"
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    message.content_subtype = "html"
    message.send(fail_silently=True)
