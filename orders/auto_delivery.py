"""Auto-entrega de pedidos para distribuidores aprobados.

Cuando un distribuidor confirma el pago (Yape, Mercado Pago, manual), el
pedido se entrega solo: para cada `OrderItem` se toma el primer
`StockItem` AVAILABLE del producto (igualando plan o stock genérico),
se marca como `SOLD`, se vincula al item y se copia el texto de
credenciales. Si todos los items consiguen stock, el pedido pasa
**directamente** a `DELIVERED` (sin tocar `PREPARING`) para evitar
que se dispare el email "Estamos preparando" además del de entrega.
Si falta stock para alguno, el pedido se queda intacto y se manda
alerta a Telegram al admin para que el caller decida si lo deja en
`PREPARING` o lo trabaja manual.

Para cliente final (no distribuidor) no se hace nada — la entrega sigue
siendo manual.
"""

from __future__ import annotations

import logging

from django.db import models, transaction
from django.utils import timezone

from . import telegram
from .models import Order

logger = logging.getLogger(__name__)


def _is_distributor_order(order: Order) -> bool:
    user = order.user
    return bool(user and getattr(user, "is_distributor", False))


def auto_deliver_distributor_order(
    order: Order, *, paid_at=None
) -> tuple[bool, list[str]]:
    """Intenta entregar automáticamente un pedido de distribuidor.

    Devuelve ``(delivered, missing)``:

    - ``delivered`` es ``True`` si el pedido quedó en estado
      ``DELIVERED`` con stock asignado y marcado como vendido. En ese
      caso el signal de transición de status dispara el email con las
      credenciales — el caller no debe enviar ningún otro correo.
    - ``missing`` es la lista de items para los que no había stock.
      En este caso el pedido NO se modifica; el caller decide si lo
      pasa a ``PREPARING`` o lo deja como estaba.

    Si el pedido no es de un distribuidor aprobado, devuelve
    ``(False, [])`` sin tocar nada — la entrega sigue siendo manual.

    Si se pasa ``paid_at`` y el pedido no tiene aún ``paid_at``, se
    setea junto con la transición a ``DELIVERED`` para no perder esa
    marca cuando el pago recién se está confirmando.
    """
    if not _is_distributor_order(order):
        return False, []

    from catalog.models import StockItem

    items = list(
        order.items.select_related("product", "plan", "stock_item").all()
    )
    if not items:
        return False, []

    missing: list[str] = []
    plan: list[tuple] = []  # [(item, stock_or_None_if_already_done), ...]
    picked_ids: list[int] = []

    with transaction.atomic():
        for item in items:
            existing = item.stock_item
            if existing is not None and existing.status == StockItem.Status.SOLD:
                # Ya entregado en una corrida previa — no hacemos nada,
                # pero contamos al item como cubierto para que el pedido
                # pueda terminar en DELIVERED.
                plan.append((item, None))
                continue

            if existing is not None and existing.status in {
                StockItem.Status.AVAILABLE,
                StockItem.Status.RESERVED,
            }:
                # Caso 1 (AVAILABLE): el admin lo vinculó a mano desde
                # el inline pero nunca se marcó vendido.
                # Caso 2 (RESERVED): el signal post_save de OrderItem
                # ya lo había reservado al crearse el pedido. En ambos
                # casos lo aprovechamos directamente.
                stock = (
                    StockItem.objects.select_for_update()
                    .filter(
                        pk=existing.pk,
                        status__in=[
                            StockItem.Status.AVAILABLE,
                            StockItem.Status.RESERVED,
                        ],
                    )
                    .first()
                )
            else:
                stock = (
                    StockItem.objects.select_for_update()
                    .filter(
                        product_id=item.product_id,
                        status=StockItem.Status.AVAILABLE,
                    )
                    .filter(
                        models.Q(plan_id=item.plan_id)
                        | models.Q(plan__isnull=True)
                    )
                    .exclude(pk__in=picked_ids)
                    .order_by("created_at")
                    .first()
                )

            if stock is None:
                missing.append(f"{item.product_name} \u2014 {item.plan_name}")
                continue

            picked_ids.append(stock.pk)
            plan.append((item, stock))

        if missing:
            # Salimos sin grabar nada — la transacción aborta cualquier
            # `select_for_update` lock.
            transaction.set_rollback(True)
        else:
            now = timezone.now()
            for item, stock in plan:
                if stock is None:
                    continue
                stock.status = StockItem.Status.SOLD
                stock.sold_at = now
                stock.save(update_fields=["status", "sold_at"])
                item.stock_item = stock
                if not item.delivered_credentials:
                    item.delivered_credentials = stock.credentials
                item.save(update_fields=["stock_item", "delivered_credentials"])

            order.status = Order.Status.DELIVERED
            order.delivered_at = now
            if order.paid_at is None:
                order.paid_at = paid_at or now
            # Limpiamos cualquier rechazo previo (caso: distri reintenta
            # tras un Yape rechazado y ahora hay stock).
            order.payment_rejection_reason = ""
            order.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "paid_at",
                    "payment_rejection_reason",
                ]
            )

    if missing:
        try:
            telegram.notify_admin(
                "\u26a0\ufe0f Pedido distribuidor "
                f"#{order.short_uuid} sin stock para: "
                + ", ".join(missing)
                + ". Cargá stock o entregalo manual desde el admin."
            )
        except Exception:
            logger.exception(
                "Fall\u00f3 notify_admin para pedido %s sin stock", order.pk
            )
        return False, missing

    return True, []
