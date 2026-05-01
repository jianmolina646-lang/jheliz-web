"""Libera reservas de stock de pedidos abandonados.

Un pedido en ``PENDING`` o ``VERIFYING`` que lleva más de N horas sin
ser pagado se considera abandonado: liberamos sus reservas para que
el stock vuelva al pool disponible.

Para correrlo periódico (cron / sistemd timer):

    python manage.py release_stale_reservations          # default 24h
    python manage.py release_stale_reservations --hours 12
    python manage.py release_stale_reservations --dry-run
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import StockItem
from orders.models import Order
from orders.stock_reservation import release_reservations_for_order


class Command(BaseCommand):
    help = (
        "Libera reservas de stock de pedidos PENDING/VERIFYING "
        "más viejos que el cutoff (default 24h)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours", type=int, default=24,
            help="Horas de antigüedad mínima para considerar un pedido abandonado.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo mostrar qué se liberaría, no escribir.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        dry = options["dry_run"]
        cutoff = timezone.now() - timedelta(hours=hours)

        stale_orders = (
            Order.objects.filter(
                status__in=[Order.Status.PENDING, Order.Status.VERIFYING],
                created_at__lt=cutoff,
                items__stock_item__status=StockItem.Status.RESERVED,
            )
            .distinct()
        )

        total_orders = 0
        total_released = 0
        for order in stale_orders:
            count = (
                order.items.filter(
                    stock_item__status=StockItem.Status.RESERVED,
                ).count()
            )
            total_orders += 1
            if dry:
                self.stdout.write(
                    f"[dry-run] Pedido #{order.short_uuid} "
                    f"(creado {order.created_at:%Y-%m-%d %H:%M}) "
                    f"tiene {count} reserva(s) que se liberarían."
                )
                total_released += count
                continue
            released = release_reservations_for_order(order)
            total_released += released
            self.stdout.write(
                f"Pedido #{order.short_uuid}: liberadas {released} reserva(s)."
            )

        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry else ''}"
            f"{total_orders} pedido(s) revisado(s), "
            f"{total_released} reserva(s) liberada(s) "
            f"(cutoff: {hours}h)."
        ))
