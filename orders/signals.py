from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from . import emails
from .models import Order


@receiver(pre_save, sender=Order)
def _order_status_transitions(sender, instance: Order, **kwargs):
    """Dispara correos al cambiar el estado del pedido desde el admin."""
    if not instance.pk:
        return
    try:
        previous = Order.objects.only("status", "delivered_at", "paid_at").get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    new = instance.status
    old = previous.status
    if old == new:
        return

    now = timezone.now()

    if new == Order.Status.PREPARING and old in {Order.Status.PAID, Order.Status.PENDING, Order.Status.VERIFYING}:
        if instance.paid_at is None:
            instance.paid_at = now
        emails.send_order_preparing(instance)

    elif new == Order.Status.DELIVERED:
        if instance.delivered_at is None:
            instance.delivered_at = now
        emails.send_order_delivered(instance)
