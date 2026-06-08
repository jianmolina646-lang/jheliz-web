"""Otorga la prueba gratis inicial a los inquilinos que aún no tienen acceso.

Los inquilinos creados antes de existir la prueba gratis quedaron con
``plan_expires_at`` vacío (les pedía pagar al instante). Esta migración les da
``Tenant.TRIAL_DAYS`` días de prueba para que puedan entrar como cualquier alta
nueva. Solo afecta a quienes nunca pagaron (``plan_expires_at`` nulo) y no están
bloqueados.
"""
from datetime import timedelta

from django.db import migrations

TRIAL_DAYS = 30


def grant_trial(apps, schema_editor):
    Tenant = apps.get_model("gestion", "Tenant")
    from django.utils import timezone

    expires = timezone.now() + timedelta(days=TRIAL_DAYS)
    Tenant.objects.filter(plan_expires_at__isnull=True, is_blocked=False).update(
        plan_expires_at=expires,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0004_assign_existing_owner"),
    ]

    operations = [
        migrations.RunPython(grant_trial, migrations.RunPython.noop),
    ]
