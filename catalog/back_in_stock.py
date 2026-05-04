"""Envío de avisos 'volvió el stock' a las alertas pendientes."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse

from .models import BackInStockAlert, Plan, Product

logger = logging.getLogger(__name__)


def _product_absolute_url(product: Product) -> str:
    return f"{settings.SITE_URL}{reverse('catalog:product', args=[product.slug])}"


def _send_alert_email(alert: BackInStockAlert) -> bool:
    """Manda el correo a una alerta puntual. Retorna True si se envió."""
    if not alert.email:
        return False
    plan_name = alert.plan.name if alert.plan_id else ""
    context = {
        "alert": alert,
        "product": alert.product,
        "plan_name": plan_name,
        "product_url": _product_absolute_url(alert.product),
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
    }
    body = render_to_string("emails/back_in_stock.html", context)
    subject = (
        f"\u00a1Volvi\u00f3 el stock! \u2014 {alert.product.name}"
        + (f" ({plan_name})" if plan_name else "")
    )
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[alert.email],
    )
    message.content_subtype = "html"
    try:
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "No se pudo enviar back-in-stock alert id=%s a %s",
            alert.pk, alert.email,
        )
        return False


def notify_pending_alerts(product: Product, plan: Plan | None = None) -> int:
    """Notifica a los suscriptores pendientes para ``product`` (y opcionalmente
    para ese ``plan``).

    Si ``plan`` es ``None``, se interpreta como "stock genérico que sirve
    para cualquier plan del producto", entonces se notifica a TODAS las
    alertas pendientes del producto (sin importar plan).

    Si ``plan`` está dado, se notifica a:
    - alertas con plan == ``plan`` (suscripciones específicas a ese plan).
    - alertas con plan == NULL (suscripciones "cualquier plan").

    Retorna la cantidad de correos enviados con éxito.
    """
    qs = BackInStockAlert.objects.filter(
        product=product, status=BackInStockAlert.Status.PENDING,
    )
    if plan is not None:
        qs = qs.filter(Q(plan=plan) | Q(plan__isnull=True))
    sent = 0
    for alert in qs.select_related("product", "plan"):
        if _send_alert_email(alert):
            alert.mark_notified()
            sent += 1
    return sent
