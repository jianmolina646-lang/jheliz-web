from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("codes", "0003_codebotclient_expires_at_codedelivery")]

    operations = [
        migrations.AddField(
            model_name="codedelivery",
            name="payload_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name="Huella del resultado"),
        ),
        migrations.AddField(
            model_name="codedelivery",
            name="duplicate",
            field=models.BooleanField(default=False, verbose_name="Resultado repetido"),
        ),
    ]
