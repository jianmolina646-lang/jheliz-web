import config.private_storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0026_merge_control_activity_branches")]

    operations = [
        migrations.AddField(
            model_name="tenantpayment",
            name="method",
            field=models.CharField(
                choices=[("binance_pay", "Binance Pay")],
                default="binance_pay",
                max_length=24,
                verbose_name="Método",
            ),
        ),
        migrations.AlterField(
            model_name="tenantpayment",
            name="proof",
            field=models.ImageField(
                blank=True,
                help_text="Captura del pago subida por el inquilino.",
                storage=config.private_storage.private_media_storage,
                upload_to="jheliz_control/pagos/",
                verbose_name="Comprobante",
            ),
        ),
        migrations.AlterModelOptions(
            name="tenantpayment",
            options={"ordering": ["-created_at"], "verbose_name": "Pago de alquiler", "verbose_name_plural": "Pagos de alquiler"},
        ),
    ]
