"""Reserva de stock al crear el pedido — previene doble venta.

Cuando se crea un ``OrderItem`` (desde el checkout web, desde un admin,
desde una API o desde un signal), se busca el primer ``StockItem``
``AVAILABLE`` que coincida con el producto+plan (o stock genérico del
producto) y se marca como ``RESERVED`` vinculándolo al item. Si dos
clientes piden la misma cuenta al mismo tiempo, el ``select_for_update``
asegura que solo uno se la lleve y el otro reciba ``stock_item=None``
(queda esperando a que el admin cargue más stock).

Cuando un pedido pasa a ``CANCELED``, ``FAILED`` o ``REFUNDED``, las
reservas de sus items vuelven a ``AVAILABLE`` y se desvinculan, para
que el stock vuelva al pool del catálogo.

La transición ``RESERVED → SOLD`` la hacen ``auto_deliver_distributor_order``
o el flujo manual de ``deliver_view`` cuando el admin entrega
credenciales: ahí sí cae el ``sold_at``.
"""

from __future__ import annotations

import logging

from django.db import models, transaction

logger = logging.getLogger(__name__)


def reserve_stock_for_item(order_item) -> bool:
    """Intenta reservar un ``StockItem`` para el ``OrderItem`` dado.

    Devuelve ``True`` si se reservó stock (y el ``OrderItem`` quedó
    vinculado), ``False`` si no había stock disponible o el item ya
    tenía un stock asociado.

    Pensado para correr durante la creación del pedido. Es seguro
    llamarlo varias veces: si el item ya tiene ``stock_item`` no hace
    nada (idempotente).
    """
    from catalog.models import StockItem

    if order_item.stock_item_id is not None:
        return False
    if order_item.product_id is None:
        return False

    with transaction.atomic():
        stock = (
            StockItem.objects.select_for_update(skip_locked=True)
            .filter(
                product_id=order_item.product_id,
                status=StockItem.Status.AVAILABLE,
            )
            .filter(
                models.Q(plan_id=order_item.plan_id)
                | models.Q(plan__isnull=True)
            )
            .order_by("created_at")
            .first()
        )
        if stock is None:
            return False

        stock.status = StockItem.Status.RESERVED
        stock.save(update_fields=["status"])
        # No usamos save() del item para evitar disparar de nuevo el
        # signal post_save y entrar en bucle.
        type(order_item).objects.filter(pk=order_item.pk).update(
            stock_item=stock
        )
        order_item.stock_item = stock
        order_item.stock_item_id = stock.pk
    logger.debug(
        "Reservado StockItem %s para OrderItem %s (producto=%s plan=%s)",
        stock.pk, order_item.pk, order_item.product_id, order_item.plan_id,
    )
    return True


def release_reservations_for_order(order) -> int:
    """Libera todas las reservas activas (RESERVED) del pedido.

    Devuelve la cantidad de stocks liberados. No toca StockItems en
    ``SOLD`` o ``DEFECTIVE`` — esos son ventas/caídas reales.
    """
    from catalog.models import StockItem

    released = 0
    with transaction.atomic():
        items = (
            order.items.select_related("stock_item")
            .filter(stock_item__isnull=False)
        )
        for item in items:
            stock = item.stock_item
            if stock is None or stock.status != StockItem.Status.RESERVED:
                continue
            # Lock + revalidación: garantizamos que entre el SELECT y el
            # UPDATE nadie marcó el stock como SOLD desde otro flujo.
            locked = (
                StockItem.objects.select_for_update()
                .filter(pk=stock.pk, status=StockItem.Status.RESERVED)
                .first()
            )
            if locked is None:
                continue
            locked.status = StockItem.Status.AVAILABLE
            locked.save(update_fields=["status"])
            type(item).objects.filter(pk=item.pk).update(stock_item=None)
            item.stock_item = None
            item.stock_item_id = None
            released += 1
    if released:
        logger.info(
            "Liberadas %d reserva(s) del pedido %s", released, order.pk,
        )
    return released
