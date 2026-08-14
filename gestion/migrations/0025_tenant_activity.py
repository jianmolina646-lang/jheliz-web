from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0024_tenant_is_demo"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="last_activity_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Última actividad"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="last_activity_path",
            field=models.CharField(blank=True, max_length=200, verbose_name="Última sección"),
        ),
    ]
