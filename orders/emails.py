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


def send_review_requests(order) -> None:
    """Crea tokens de rese\u00f1a y env\u00eda un correo con magic links.

    Una rese\u00f1a por cada producto comprado en el pedido. El cliente entra al
    link, escribe rating + comentario opcional con foto y queda en estado
    ``pending`` para moderaci\u00f3n.
    """
    if not order.email:
        return

    from catalog.models import ProductReview  # local import to avoid circular

    items = list(order.items.select_related("plan__product").all())
    if not items:
        return

    review_links = []
    seen_products = set()
    for item in items:
        plan = getattr(item, "plan", None)
        if not plan:
            continue
        product = plan.product
        if product.id in seen_products:
            continue
        seen_products.add(product.id)
        review = (
            ProductReview.objects
            .filter(order=order, product=product)
            .first()
        )
        if review is None:
            review = ProductReview.objects.create(
                product=product,
                order=order,
                user=order.user,
                author_name=(order.user.first_name if order.user else "") or "Cliente",
                email=order.email,
                rating=5,
                comment="",
                status=ProductReview.Status.PENDING,
                is_verified=True,
            )
        review_links.append({
            "product": product,
            "url": f"{settings.SITE_URL}{reverse('catalog:review_submit', args=[review.token])}",
        })

    if not review_links:
        return

    context = {
        "order": order,
        "review_links": review_links,
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
    }
    body = render_to_string("emails/review_request.html", context)
    message = EmailMessage(
        subject=f"\u00bfQu\u00e9 te pareci\u00f3 tu compra? \u2014 #{order.short_uuid}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    message.content_subtype = "html"
    message.send(fail_silently=True)
