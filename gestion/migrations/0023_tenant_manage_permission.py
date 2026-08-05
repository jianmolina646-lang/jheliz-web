from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0022_database_hardening"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="tenant",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "manage_tenants",
                        "Puede administrar todos los inquilinos y sus pagos",
                    )
                ],
                "verbose_name": "Inquilino",
                "verbose_name_plural": "Inquilinos",
            },
        ),
    ]
