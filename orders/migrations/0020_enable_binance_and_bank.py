"""Habilita Binance Pay (con el QR del comerciante) y el depósito bancario
(Ecuador) en la configuración de pagos. El QR viene commiteado en
static/img/payments/binance_qr.jpg y se copia al storage de media.
"""

import os

from django.conf import settings
from django.core.files import File
from django.db import migrations

BANK_ACCOUNTS = (
    "Banco Guayaquil — Cuenta de Ahorros 0022156352\n"
    "Banco Pichincha — Cuenta de Ahorros 2205839104"
)


def enable_methods(apps, schema_editor):
    PaymentSettings = apps.get_model("orders", "PaymentSettings")
    obj, _ = PaymentSettings.objects.get_or_create(pk=1)

    obj.bank_enabled = True
    if not obj.bank_accounts:
        obj.bank_accounts = BANK_ACCOUNTS

    obj.binance_enabled = True
    if not obj.binance_qr:
        qr_path = os.path.join(
            settings.BASE_DIR, "static", "img", "payments", "binance_qr.jpg"
        )
        if os.path.exists(qr_path):
            with open(qr_path, "rb") as fh:
                obj.binance_qr.save("binance_qr.jpg", File(fh), save=False)
    obj.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0019_remove_paymentsettings_yape_enabled_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_methods, noop),
    ]
