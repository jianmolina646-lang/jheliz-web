"""Crea las dos categorías base (Streaming, Licencias) si aún no existen.

Sirve como red de seguridad cuando se levanta una instancia con base de
datos vacía (por ejemplo, después de migrar a un VPS nuevo). Es
idempotente: nunca duplica ni sobrescribe categorías existentes.
"""
from django.db import migrations


SEED = [
    {
        "slug": "streaming",
        "name": "Streaming",
        "emoji": "\U0001f3ac",
        "order": 1,
        "audience": "ambos",
        "description": "Cuentas de streaming por perfil o completas.",
    },
    {
        "slug": "licencias",
        "name": "Licencias",
        "emoji": "\U0001f5a5\ufe0f",
        "order": 2,
        "audience": "ambos",
        "description": "Licencias originales de software.",
    },
]


def seed(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for entry in SEED:
        Category.objects.get_or_create(
            slug=entry["slug"],
            defaults={
                "name": entry["name"],
                "emoji": entry["emoji"],
                "order": entry["order"],
                "audience": entry["audience"],
                "description": entry["description"],
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    # Borrar solo si no tiene productos asociados, para no romper data real.
    Category = apps.get_model("catalog", "Category")
    for entry in SEED:
        cat = Category.objects.filter(slug=entry["slug"]).first()
        if cat and not cat.products.exists():
            cat.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0017_backinstockalert"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
