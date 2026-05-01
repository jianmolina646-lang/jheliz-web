from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from . import emails
from .models import Order, OrderItem

# Estados terminales que liberan las reservas de stock vinculadas al
# pedido. Si el pedido cae a alguno de estos, los StockItem RESERVED
# vuelven a AVAILABLE para el resto del catálogo.
_CANCEL_STATUSES = {
    Order.Status.CANCELED,
    Order.Status.FAILED,
    Order.Status.REFUNDED,
}


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
        # Pide rese\u00f1a verificada via magic link.
        try:
            emails.send_review_requests(instance)
        except Exception:
            # No bloqueamos la entrega si falla la creaci\u00f3n de tokens.
            pass

    # Liberar reservas si el pedido se cancela / falla / se reembolsa.
    if new in _CANCEL_STATUSES and old not in _CANCEL_STATUSES:
        # Importamos acá para evitar ciclo a la carga del módulo.
        from .stock_reservation import release_reservations_for_order

        try:
            release_reservations_for_order(instance)
        except Exception:
            # No bloqueamos la transición si falla la liberación;
            # un cron / management command la puede arreglar después.
            pass


@receiver(post_save, sender=OrderItem)
def _reserve_stock_on_create(sender, instance: OrderItem, created, **kwargs):
    """Al crear un OrderItem, reservar un StockItem disponible.

    Esto previene la doble venta cuando dos clientes piden la misma
    cuenta al mismo tiempo. Si no hay stock disponible, el item queda
    sin ``stock_item`` (igual que antes) y el admin lo carga manual.
    """
    if not created:
        return
    if instance.stock_item_id is not None:
        # Caso típico: el admin asignó stock manualmente al crear.
        return

    from .stock_reservation import reserve_stock_for_item

    try:
        reserve_stock_for_item(instance)
    except Exception:
        # No bloqueamos la creación del pedido si falla la reserva;
        # el flujo manual lo cubre y los logs alertan del problema.
        import logging
        logging.getLogger(__name__).exception(
            "Falló reserva automática de stock para OrderItem %s", instance.pk,
        )
