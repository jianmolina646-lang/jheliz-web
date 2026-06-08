"""Asigna los datos existentes de Jheliz Control al primer superusuario.

Hasta ahora el módulo era de un solo dueño (el admin de la tienda). Al volverlo
multi-inquilino agregamos ``owner`` a cada modelo; esta migración asigna todas
las filas previas (servicios, clientes, suscripciones, movimientos y ajustes) al
primer superusuario para que su panel siga viéndose igual.
"""
from django.db import migrations


def assign_owner(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    owner = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )
    if owner is None:
        return

    for model_name in ("Service", "Client", "Subscription", "Transaction"):
        Model = apps.get_model("gestion", model_name)
        Model.objects.filter(owner__isnull=True).update(owner=owner)

    ControlSettings = apps.get_model("gestion", "ControlSettings")
    ControlSettings.objects.filter(owner__isnull=True).update(owner=owner)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0003_saassettings_client_owner_controlsettings_owner_and_more"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(assign_owner, noop),
    ]
