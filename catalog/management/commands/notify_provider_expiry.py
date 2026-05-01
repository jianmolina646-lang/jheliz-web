"""Avisa por Telegram cuando una cuenta de stock está por vencer en el proveedor.

Para cada `StockItem` con `provider_expires_at` cargado y status no terminal
(AVAILABLE / RESERVED), si el vencimiento cae a 3 días o menos manda alerta
una sola vez (campo `provider_expiry_3d_notified_at`). Cuando cae a 1 día o
menos, manda una segunda alerta más urgente (campo `provider_expiry_1d_notified_at`).

Uso:
    python manage.py notify_provider_expiry
    python manage.py notify_provider_expiry --dry-run

Cron sugerido (cada hora):
    7 * * * *  cd /app && python manage.py notify_provider_expiry
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import StockItem
from orders import telegram


class Command(BaseCommand):
    help = (
        "Alerta por Telegram cuando un StockItem con provider_expires_at "
        "está a 3 días o 1 día de vencer."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry_run: bool = opts["dry_run"]
        now = timezone.now()
        in_3d = now + timedelta(days=3)
        in_1d = now + timedelta(days=1)

        active_statuses = [
            StockItem.Status.AVAILABLE,
            StockItem.Status.RESERVED,
        ]

        # 3-day notice: vence dentro de las próximas 72h (pero no
        # ya en las próximas 24h, esas las cubre el aviso urgente).
        soon = StockItem.objects.filter(
            status__in=active_statuses,
            provider_expires_at__isnull=False,
            provider_expires_at__lte=in_3d,
            provider_expires_at__gt=in_1d,
            provider_expiry_3d_notified_at__isnull=True,
        ).select_related("product", "plan")

        # 1-day urgent: vence dentro de las próximas 24h.
        urgent = StockItem.objects.filter(
            status__in=active_statuses,
            provider_expires_at__isnull=False,
            provider_expires_at__lte=in_1d,
            provider_expiry_1d_notified_at__isnull=True,
        ).select_related("product", "plan")

        sent_3d = 0
        for stock in soon:
            msg = (
                f"⚠️ Cuenta vence en proveedor pronto (≤3d)\n"
                f"Producto: {stock.product.name}"
                f"{f' — {stock.plan.name}' if stock.plan else ''}\n"
                f"Vence: {stock.provider_expires_at:%Y-%m-%d %H:%M}\n"
                f"Estado: {stock.get_status_display()}\n"
                f"ID: #{stock.pk}"
            )
            if dry_run:
                self.stdout.write(f"[dry-run] 3d: {msg}")
            else:
                telegram.notify_admin(msg)
                stock.provider_expiry_3d_notified_at = now
                stock.save(update_fields=["provider_expiry_3d_notified_at"])
            sent_3d += 1

        sent_1d = 0
        for stock in urgent:
            msg = (
                f"🔥 URGENTE: cuenta vence en proveedor en <24h\n"
                f"Producto: {stock.product.name}"
                f"{f' — {stock.plan.name}' if stock.plan else ''}\n"
                f"Vence: {stock.provider_expires_at:%Y-%m-%d %H:%M}\n"
                f"Estado: {stock.get_status_display()}\n"
                f"ID: #{stock.pk}\n"
                f"Acción: rotar la cuenta antes del vencimiento."
            )
            if dry_run:
                self.stdout.write(f"[dry-run] 1d: {msg}")
            else:
                telegram.notify_admin(msg)
                stock.provider_expiry_1d_notified_at = now
                stock.save(update_fields=["provider_expiry_1d_notified_at"])
            sent_1d += 1

        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry_run else ''}"
            f"Avisos enviados: {sent_3d} de 3d, {sent_1d} urgentes (1d)."
        ))
