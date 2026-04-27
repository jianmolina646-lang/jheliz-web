"""Manda recordatorios de vencimiento a los clientes.

Por defecto envía dos ventanas: 3 días antes y 1 día antes del vencimiento.
Es idempotente: cada item lleva su propia marca de tiempo de envío.

Uso:
    python manage.py send_expiry_reminders            # produce envíos
    python manage.py send_expiry_reminders --dry-run  # sólo lista
    python manage.py send_expiry_reminders --windows 7,3,1   # ventanas custom

Configurar como cron diario (ej. en crontab del server o en el scheduler de Fly):
    0 9 * * *  cd /app && python manage.py send_expiry_reminders
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders import emails
from orders.models import Order, OrderItem


# Mapa: ventana en días -> nombre del campo donde marcamos el envío
_FIELD_MAP = {
    3: "expiry_reminder_3d_sent_at",
    1: "expiry_reminder_1d_sent_at",
}


class Command(BaseCommand):
    help = "Envía recordatorios de vencimiento a clientes (3 y 1 día antes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No envía correos; sólo imprime lo que haría.",
        )
        parser.add_argument(
            "--windows", default="3,1",
            help="Ventanas en días, separadas por coma. Default: 3,1.",
        )

    def handle(self, *args, **opts):
        dry_run: bool = opts["dry_run"]
        windows = [int(w.strip()) for w in opts["windows"].split(",") if w.strip()]
        for w in windows:
            if w not in _FIELD_MAP:
                self.stderr.write(self.style.ERROR(
                    f"Ventana {w} no soportada. Soportadas: {sorted(_FIELD_MAP)}"
                ))
                return

        now = timezone.now()
        total_sent = 0

        for days_left in windows:
            window_start = now + timedelta(days=days_left - 1, hours=12)
            window_end = now + timedelta(days=days_left + 1, hours=12)
            field = _FIELD_MAP[days_left]

            qs = (
                OrderItem.objects
                .select_related("order")
                .filter(
                    order__status__in=[
                        Order.Status.DELIVERED,
                        Order.Status.PREPARING,
                    ],
                    expires_at__gte=window_start,
                    expires_at__lt=window_end,
                    **{f"{field}__isnull": True},
                )
                .exclude(order__email="")
            )

            # Agrupa por pedido para mandar un solo email cuando varios items
            # del mismo pedido vencen el mismo día.
            by_order: dict[int, list[OrderItem]] = defaultdict(list)
            for item in qs:
                by_order[item.order_id].append(item)

            for order_id, items in by_order.items():
                order = items[0].order
                self.stdout.write(
                    f"  → ventana {days_left}d: pedido #{order.short_uuid} "
                    f"({order.email}) — {len(items)} item(s)"
                )
                if dry_run:
                    continue
                emails.send_expiry_reminder(order, items, days_left)
                ts = timezone.now()
                OrderItem.objects.filter(pk__in=[i.pk for i in items]).update(**{field: ts})
                total_sent += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no se enviaron correos."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Recordatorios enviados: {total_sent} pedido(s)."
            ))
