from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0023_tenant_manage_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                help_text="Cuenta temporal de demostración con operaciones de escritura bloqueadas.",
                verbose_name="Demo",
            ),
        ),
    ]
