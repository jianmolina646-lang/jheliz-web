from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("codes", "0003_codebotclient_expires_at_codedelivery"),
    ]

    operations = [
        migrations.AddField(
            model_name="botstate",
            name="daily_limit",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Vacío = usar CODES_DAILY_LIMIT de la configuración.",
                null=True,
                verbose_name="Límite diario de consultas",
            ),
        ),
    ]
