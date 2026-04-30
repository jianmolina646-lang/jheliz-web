"""Manda recordatorios de vencimiento a los clientes y distribuidores.

- Clientes finales: por defecto envía dos ventanas, 3 días antes y 1 día antes.
- Distribuidores aprobados: por defecto envía tres ventanas (7, 3 y 1 día antes)
  con copy específico que menciona a sus clientes finales y linkea al panel
  mayorista.

Es idempotente: cada item lleva su propia marca de tiempo de envío por ventana.

Uso:
    python manage.py send_expiry_reminders            # produce envíos
    python manage.py send_expiry_reminders --dry-run  # sólo lista
    python manage.py send_expiry_reminders --windows 7,3,1            # ventanas cliente
    python manage.py send_expiry_reminders --distri-windows 7,3,1     # ventanas distri

Cron diario sugerido:
    0 9 * * *  cd /app && python manage.py send_expiry_reminders
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders import emails, telegram
from orders.models import Order, OrderItem


# Mapa: ventana en días -> nombre del campo donde marcamos el envío
_CUSTOMER_FIELD_MAP = {
    3: "expiry_reminder_3d_sent_at",
    1: "expiry_reminder_1d_sent_at",
}
_DISTRI_FIELD_MAP = {
    7: "distri_reminder_7d_sent_at",
    3: "distri_reminder_3d_sent_at",
    1: "distri_reminder_1d_sent_at",
}


class Command(BaseCommand):
    help = "Envía recordatorios de vencimiento a clientes y distribuidores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No envía correos; sólo imprime lo que haría.",
        )
        parser.add_argument(
            "--windows", default="3,1",
            help="Ventanas cliente final, separadas por coma. Default: 3,1.",
        )
        parser.add_argument(
            "--distri-windows", default="7,3,1",
            help="Ventanas distribuidor, separadas por coma. Default: 7,3,1.",
        )
        parser.add_argument(
            "--skip-customers", action="store_true",
            help="No procesa recordatorios de clientes finales (sólo distribuidores).",
        )
        parser.add_argument(
            "--skip-distributors", action="store_true",
            help="No procesa recordatorios de distribuidores (sólo clientes).",
        )

    def _parse_windows(self, raw: str, allowed: dict) -> list[int]:
        parsed = [int(w.strip()) for w in raw.split(",") if w.strip()]
        for w in parsed:
            if w not in allowed:
                raise ValueError(
                    f"Ventana {w} no soportada. Soportadas: {sorted(allowed)}"
                )
        return parsed

    def _process(
        self,
        *,
        days_left: int,
        field: str,
        for_distributor: bool,
        dry_run: bool,
    ) -> tuple[int, int]:
        """Devuelve (orders_avisadas, items_avisados)."""
        now = timezone.now()
        window_start = now + timedelta(days=days_left - 1, hours=12)
        window_end = now + timedelta(days=days_left + 1, hours=12)

        qs = (
            OrderItem.objects
            .select_related("order", "order__user")
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
        if for_distributor:
            qs = qs.filter(
                order__user__role="distribuidor",
                order__user__distributor_approved=True,
            )
        else:
            # Clientes finales: cualquier pedido cuyo dueño NO sea distribuidor
            # aprobado (incluye guests sin user).
            qs = qs.exclude(
                order__user__role="distribuidor",
                order__user__distributor_approved=True,
            )

        by_order: dict[int, list[OrderItem]] = defaultdict(list)
        for item in qs:
            by_order[item.order_id].append(item)

        orders_count = 0
        items_count = 0
        for order_id, items in by_order.items():
            order = items[0].order
            tag = "distri" if for_distributor else "cliente"
            self.stdout.write(
                f"  → ventana {days_left}d ({tag}): pedido #{order.short_uuid} "
                f"({order.email}) — {len(items)} item(s)"
            )
            if dry_run:
                continue
            emails.send_expiry_reminder(order, items, days_left, for_distributor=for_distributor)
            ts = timezone.now()
            OrderItem.objects.filter(pk__in=[i.pk for i in items]).update(**{field: ts})
            orders_count += 1
            items_count += len(items)
        return orders_count, items_count

    def handle(self, *args, **opts):
        dry_run: bool = opts["dry_run"]

        try:
            customer_windows = self._parse_windows(opts["windows"], _CUSTOMER_FIELD_MAP)
            distri_windows = self._parse_windows(opts["distri_windows"], _DISTRI_FIELD_MAP)
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        total_orders = 0
        total_distri_items = 0

        if not opts["skip_customers"]:
            for w in customer_windows:
                orders, _items = self._process(
                    days_left=w,
                    field=_CUSTOMER_FIELD_MAP[w],
                    for_distributor=False,
                    dry_run=dry_run,
                )
                total_orders += orders

        if not opts["skip_distributors"]:
            for w in distri_windows:
                orders, items = self._process(
                    days_left=w,
                    field=_DISTRI_FIELD_MAP[w],
                    for_distributor=True,
                    dry_run=dry_run,
                )
                total_orders += orders
                total_distri_items += items

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no se enviaron correos."))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Recordatorios enviados: {total_orders} pedido(s)."
        ))
        # Aviso al admin por Telegram con resumen del run del día (best-effort).
        if total_distri_items > 0:
            try:
                telegram.notify_admin(
                    f"📅 Recordatorios distribuidor enviados hoy: "
                    f"{total_distri_items} cuenta(s) por vencer."
                )
            except Exception:  # nunca rompe el cron por culpa de Telegram
                pass
