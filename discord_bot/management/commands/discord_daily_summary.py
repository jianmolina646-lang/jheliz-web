"""Postea el resumen diario en el canal ``#📊-dashboard`` de Discord.

Diseñado para correr como cron job una vez al día (típicamente a las 9 AM
hora Lima). Reporta el día anterior con métricas clave: ventas totales,
pedidos nuevos, conversión, top productos y pendientes vivos.

Uso:

    python manage.py discord_daily_summary
    python manage.py discord_daily_summary --days-back 0   # del día actual
    python manage.py discord_daily_summary --dry-run       # imprime, no postea
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone


COLOR_SUCCESS = 0x22C55E


class Command(BaseCommand):
    help = "Postea el resumen diario en el canal #📊-dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-back", type=int, default=1,
            help="Cuántos días para atrás reportar (1 = ayer; 0 = hoy parcial).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No envía el mensaje, sólo imprime el contenido.",
        )

    def handle(self, *args, **opts):
        from discord_bot import client, notifications

        days_back = int(opts.get("days_back", 1))
        dry_run = opts.get("dry_run", False)

        now = timezone.localtime()
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        if days_back == 0:
            start = end
            end = now
            label = "Hoy (parcial)"
        else:
            label = (start).strftime("%A %d/%m").capitalize()
            # Si pidieron más días atrás, ajustamos.
            if days_back > 1:
                start = end - timedelta(days=days_back)

        title, description, fields = self._build_payload(start, end, label)
        self.stdout.write(self.style.SUCCESS(title))
        for f in fields:
            self.stdout.write(f"  {f['name']}: {f['value']}")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: no se envió a Discord"))
            return

        channel_id = notifications._channel("dashboard")
        if not channel_id:
            self.stderr.write(self.style.WARNING(
                "DISCORD_CHANNEL_DASHBOARD vacío en .env — saltando envío."
            ))
            return

        msg = client.send_embed(
            channel_id,
            title=title,
            description=description,
            fields=fields,
            color=COLOR_SUCCESS,
            footer=f"Generado automáticamente · {now.strftime('%d/%m %H:%M')}",
        )
        if msg:
            self.stdout.write(self.style.SUCCESS("Resumen enviado a #dashboard."))
        else:
            self.stderr.write(self.style.ERROR("No pude enviar el resumen."))

    def _build_payload(self, start, end, label):
        from orders.models import Order, OrderItem

        qs = Order.objects.filter(created_at__gte=start, created_at__lt=end)
        total = qs.count()
        by_status = dict(qs.values_list("status").annotate(n=Count("id")))
        delivered = by_status.get(Order.Status.DELIVERED, 0)
        pending = sum(by_status.get(s, 0) for s in (
            Order.Status.PENDING,
            Order.Status.VERIFYING,
            Order.Status.PAID,
            Order.Status.PREPARING,
        ))

        paid_qs = qs.filter(status__in=(
            Order.Status.PAID,
            Order.Status.PREPARING,
            Order.Status.DELIVERED,
        ))
        rev_pen = paid_qs.filter(currency="PEN").aggregate(s=Sum("total"))["s"] or 0
        rev_usd = paid_qs.filter(currency="USD").aggregate(s=Sum("total"))["s"] or 0

        conv = "—"
        if total:
            conv = f"{(delivered / total) * 100:.0f}%"

        top = list(
            OrderItem.objects.filter(order__in=paid_qs)
            .values("product_name")
            .annotate(qty=Sum("quantity"))
            .order_by("-qty")[:3]
        )

        # Pendientes vivos (todos los abiertos, no solo del período).
        live_pending = Order.objects.filter(status__in=(
            Order.Status.PENDING,
            Order.Status.VERIFYING,
            Order.Status.PAID,
            Order.Status.PREPARING,
        )).count()

        fields = [
            {"name": "📦 Pedidos del día", "value": f"**{total}** · {delivered} entregados · {pending} aún pendientes", "inline": False},
            {"name": "💰 Facturación", "value": f"**PEN {rev_pen}** · USD {rev_usd}", "inline": True},
            {"name": "🎯 Conversión", "value": f"**{conv}**", "inline": True},
            {"name": "⏳ Cola viva", "value": f"**{live_pending}** pedidos abiertos en total", "inline": True},
        ]
        if top:
            top_str = "\n".join(
                f"`{i+1}.` **{t['product_name'][:32]}** — {t['qty']}"
                for i, t in enumerate(top)
            )
            fields.append({"name": "🏆 Top productos", "value": top_str, "inline": False})

        title = f"📊 Resumen · {label}"
        description = f"Período: `{start.strftime('%d/%m %H:%M')}` → `{end.strftime('%d/%m %H:%M')}`"
        return title, description, fields
