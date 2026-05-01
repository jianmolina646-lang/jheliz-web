"""Reconcilia el stock vendido cuyo `StockItem.status` no quedó en `SOLD`.

Caso típico: el admin entregó un pedido de distribuidor a mano (vinculó el
``StockItem`` desde el inline o tipeó las credenciales sin clickear el
botón de stock). El pedido quedó en ``DELIVERED`` pero el ``StockItem``
sigue como ``AVAILABLE``, por lo que en *Stock por producto* no aparece
como vendido.

Este comando recorre los ``OrderItem`` de pedidos ``DELIVERED`` y, para
cada uno cuyo ``stock_item`` está vinculado pero su status no es
``SOLD``, lo marca como vendido y le pone ``sold_at``.

Si se pasa ``--match-by-credentials`` también intenta vincular items sin
``stock_item`` cuyo texto de ``delivered_credentials`` coincide
exactamente con el texto de un ``StockItem`` ``AVAILABLE`` del mismo
producto — útil para arreglar entregas viejas donde el admin tipeó las
credenciales a mano.

Uso::

    python manage.py reconcile_sold_stock              # solo los ya linkeados
    python manage.py reconcile_sold_stock --match-by-credentials
    python manage.py reconcile_sold_stock --dry-run    # no escribe nada

Cron sugerido (semanal, todos los lunes a las 3am)::

    0 3 * * 1  cd /app && /app/.venv/bin/python manage.py reconcile_sold_stock

Es idempotente: si no encuentra inconsistencias, no hace nada. Pensado
como red de seguridad por si algún flujo manual deja un StockItem en un
estado raro.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import StockItem
from orders.models import Order, OrderItem


class Command(BaseCommand):
    help = "Marca como SOLD los StockItems vinculados a pedidos entregados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--match-by-credentials",
            action="store_true",
            help=(
                "Adem\u00e1s, intenta vincular OrderItems sin stock_item cuyo texto "
                "de credenciales coincide exactamente con un StockItem AVAILABLE."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No escribe en la base de datos, solo reporta.",
        )

    def handle(self, *args, **options):
        match_by_creds: bool = options["match_by_credentials"]
        dry_run: bool = options["dry_run"]

        delivered_items = (
            OrderItem.objects
            .filter(order__status=Order.Status.DELIVERED)
            .select_related("order", "stock_item", "product")
        )

        marked_linked = 0
        linked_by_creds = 0
        skipped_no_match = 0

        with transaction.atomic():
            for item in delivered_items:
                if item.stock_item_id:
                    stock = item.stock_item
                    if stock.status != StockItem.Status.SOLD:
                        if dry_run:
                            self.stdout.write(
                                f"[dry] Stock #{stock.pk} ({stock.product.name}) "
                                f"\u2192 SOLD por pedido #{item.order.short_uuid}"
                            )
                        else:
                            stock.status = StockItem.Status.SOLD
                            stock.sold_at = stock.sold_at or (
                                item.order.delivered_at or timezone.now()
                            )
                            stock.save(update_fields=["status", "sold_at"])
                        marked_linked += 1
                    continue

                if not match_by_creds:
                    continue

                creds = (item.delivered_credentials or "").strip()
                if not creds:
                    continue

                candidate = (
                    StockItem.objects
                    .filter(
                        product_id=item.product_id,
                        status=StockItem.Status.AVAILABLE,
                        credentials=creds,
                    )
                    .order_by("created_at")
                    .first()
                )
                if candidate is None:
                    skipped_no_match += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[dry] Vincular Stock #{candidate.pk} "
                        f"({candidate.product.name}) a pedido "
                        f"#{item.order.short_uuid} y marcar SOLD"
                    )
                else:
                    candidate.status = StockItem.Status.SOLD
                    candidate.sold_at = candidate.sold_at or (
                        item.order.delivered_at or timezone.now()
                    )
                    candidate.save(update_fields=["status", "sold_at"])
                    item.stock_item = candidate
                    item.save(update_fields=["stock_item"])
                linked_by_creds += 1

            if dry_run:
                transaction.set_rollback(True)

        verb = "Se marcar\u00edan" if dry_run else "Marcados"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {marked_linked} StockItem(s) ya vinculado(s) como SOLD."
        ))
        if match_by_creds:
            verb2 = "Se vincular\u00edan" if dry_run else "Vinculados"
            self.stdout.write(self.style.SUCCESS(
                f"{verb2} {linked_by_creds} OrderItem(s) por coincidencia de credenciales."
            ))
            if skipped_no_match:
                self.stdout.write(
                    f"{skipped_no_match} OrderItem(s) sin stock_item no tuvieron match."
                )
