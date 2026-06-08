from django.db import migrations


def seed_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("gestion", "ServiceCategory")
    defaults = [
        ("TV y Cine", "tv-cine", "live_tv", 1),
        ("Música", "musica", "music_note", 2),
        ("Diseño y Educación", "diseno-educacion", "palette", 3),
        ("VPN y Proxy", "vpn-proxy", "vpn_lock", 4),
    ]
    for name, slug, icon, order in defaults:
        ServiceCategory.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "icon": icon, "order": order},
        )


def unseed(apps, schema_editor):
    ServiceCategory = apps.get_model("gestion", "ServiceCategory")
    ServiceCategory.objects.filter(
        slug__in=["tv-cine", "musica", "diseno-educacion", "vpn-proxy"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed),
    ]
