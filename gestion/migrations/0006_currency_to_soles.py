"""Cambia la moneda por defecto del SaaS de USD a soles (S/).

El módulo Jheliz Control arrancó con ``currency="USD"`` por defecto, pero el
negocio opera en Perú (Yape, precios en S/). Esta migración pasa a ``"S/"`` los
registros que quedaron en USD: los ajustes de cada inquilino y las
suscripciones/movimientos ya cargados.
"""
from django.db import migrations


def usd_to_soles(apps, schema_editor):
    for model_name in ("ControlSettings", "Subscription", "Transaction"):
        Model = apps.get_model("gestion", model_name)
        Model.objects.filter(currency="USD").update(currency="S/")


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0005_trial_for_existing_tenants"),
    ]

    operations = [
        migrations.RunPython(usd_to_soles, migrations.RunPython.noop),
    ]
