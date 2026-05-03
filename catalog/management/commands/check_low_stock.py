"""Avisa por Telegram cuando un Plan tiene stock bajo el umbral.

Antispam: no vuelve a alertar sobre el mismo Plan en menos de 6 horas.
Si el stock vuelve a subir por encima del umbral y luego baja otra vez,
se vuelve a alertar.

Uso:
    python manage.py check_low_stock
    python manage.py check_low_stock --dry-run

Cron sugerido (cada 30 min):
    */30 * * * *  cd /app && python manage.py check_low_stock
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import Plan, StockItem
from orders import telegram


_REALERT_AFTER = timedelta(hours=6)


class Command(BaseCommand):
    help = "Alerta por Telegram cuando un plan tiene stock bajo el umbral."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry_run: bool = opts["dry_run"]
        now = timezone.now()

        plans = (
            Plan.objects
            .filter(is_active=True, product__is_active=True)
            .select_related("product")
            .annotate(
                _avail=Count(
                    "stock_items",
                    filter=Q(stock_items__status=StockItem.Status.AVAILABLE),
                )
            )
        )

        below: list[tuple[Plan, int]] = []
        recovered: list[Plan] = []
        for plan in plans:
            available = plan._avail
            threshold = plan.low_stock_threshold or 0
            if threshold <= 0:
                continue
            if available < threshold:
                # ¿Ya alertamos hace poco?
                if (
                    plan.low_stock_alert_sent_at
                    and now - plan.low_stock_alert_sent_at < _REALERT_AFTER
                ):
                    continue
                below.append((plan, available))
            elif plan.low_stock_alert_sent_at is not None and available >= threshold:
                # Stock recuperado: limpia el flag para que la próxima caída
                # se vuelva a alertar inmediatamente.
                recovered.append(plan)

        if not below and not recovered:
            self.stdout.write("Sin cambios — no hay alertas pendientes.")
            return

        if below:
            lines = ["<b>⚠️ Stock bajo</b>", ""]
            for plan, available in below:
                lines.append(
                    f"• <b>{plan.product.name}</b> — {plan.name}: "
                    f"{available}/{plan.low_stock_threshold}"
                )
            text = "\n".join(lines)
            self.stdout.write(text.replace("<b>", "").replace("</b>", ""))
            if not dry_run:
                if telegram.is_configured():
                    telegram.notify_admin(text)
                Plan.objects.filter(pk__in=[p.pk for p, _ in below]).update(
                    low_stock_alert_sent_at=now
                )

        if recovered and not dry_run:
            Plan.objects.filter(pk__in=[p.pk for p in recovered]).update(
                low_stock_alert_sent_at=None
            )
            self.stdout.write(
                self.style.SUCCESS(f"Stock recuperado en {len(recovered)} plan(es).")
            )
            # Publica al canal una vez por producto (evita spam si recuperan
            # varios planes del mismo producto a la vez).
            if telegram.channel_is_configured():
                announced: set[int] = set()
                for plan in recovered:
                    if plan.product_id in announced:
                        continue
                    announced.add(plan.product_id)
                    try:
                        telegram.announce_product(plan.product, kind="restock")
                    except Exception:
                        self.stdout.write(
                            self.style.WARNING(
                                f"No se pudo anunciar restock de {plan.product.name}"
                            )
                        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no se enviaron mensajes."))
