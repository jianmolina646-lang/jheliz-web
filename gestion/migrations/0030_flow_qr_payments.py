from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0029_tenantpayment_paid_at_tenantpayment_payer_name_and_more")]

    operations = [
        migrations.AlterField(
            model_name="tenantpayment", name="method",
            field=models.CharField(
                max_length=24,
                choices=[("yape", "Yape"), ("binance_pay", "Binance Pay"), ("flow_qr", "QR interoperable (Flow)")],
                default="yape", verbose_name="Método",
            ),
        ),
        migrations.AddField(model_name="tenantpayment", name="provider_order_id", field=models.CharField(blank=True, editable=False, max_length=40, null=True, unique=True)),
        migrations.AddField(model_name="tenantpayment", name="provider_token", field=models.CharField(blank=True, editable=False, max_length=160, null=True, unique=True)),
        migrations.AddField(model_name="tenantpayment", name="provider_flow_order", field=models.BigIntegerField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name="tenantpayment", name="provider_payload", field=models.JSONField(blank=True, default=dict, editable=False)),
    ]
