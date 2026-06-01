from datetime import timedelta

from django.db import migrations


def backfill_expires_at(apps, schema_editor):
    """Calcula el vencimiento de ventas viejas que quedaron sin ``expires_at``.

    Antes, las cuentas registradas a mano (Telegram/WhatsApp/manual) no
    guardaban vencimiento, así que en Control de cuentas no mostraban el
    "Vence en Xd" como las compras web. Acá lo rellenamos igual que una
    compra web: ``paid_at + plan.duration_days`` (solo cuando hay fecha de
    pago y el plan tiene duración > 0; las licencias perpetuas quedan sin
    vencer).
    """
    OrderItem = apps.get_model("orders", "OrderItem")
    qs = (
        OrderItem.objects.filter(
            expires_at__isnull=True,
            plan__isnull=False,
            plan__duration_days__gt=0,
            order__paid_at__isnull=False,
        )
        .select_related("order", "plan")
    )
    for oi in qs.iterator():
        oi.expires_at = oi.order.paid_at + timedelta(days=oi.plan.duration_days)
        oi.save(update_fields=["expires_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0017_paymentsettings_usd_rate_auto_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_expires_at, noop_reverse),
    ]
