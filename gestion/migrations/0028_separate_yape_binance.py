from django.db import migrations, models


def move_binance_out_of_yape(apps, schema_editor):
    settings_model = apps.get_model("gestion", "SaasSettings")
    for settings in settings_model.objects.all():
        settings.binance_holder = settings.yape_holder
        settings.binance_pay_id = settings.yape_phone
        settings.binance_qr = settings.yape_qr
        settings.binance_instructions = settings.instructions
        settings.yape_holder = ""
        settings.yape_phone = ""
        settings.yape_qr = ""
        settings.instructions = ""
        settings.save()


class Migration(migrations.Migration):
    dependencies = [("gestion", "0027_tenantpayment_method")]

    operations = [
        migrations.AlterField(
            model_name="tenantpayment",
            name="method",
            field=models.CharField(
                choices=[("yape", "Yape"), ("binance_pay", "Binance Pay")],
                default="yape",
                max_length=24,
                verbose_name="Método",
            ),
        ),
        migrations.AlterField(
            model_name="saassettings",
            name="yape_holder",
            field=models.CharField(blank=True, max_length=120, verbose_name="Titular Yape"),
        ),
        migrations.AlterField(
            model_name="saassettings",
            name="yape_phone",
            field=models.CharField(blank=True, max_length=30, verbose_name="Número Yape"),
        ),
        migrations.AlterField(
            model_name="saassettings",
            name="yape_qr",
            field=models.ImageField(blank=True, help_text="QR de Yape para cobrar el alquiler.", upload_to="jheliz_control/yape/", verbose_name="QR de Yape"),
        ),
        migrations.AlterField(
            model_name="saassettings",
            name="instructions",
            field=models.TextField(blank=True, verbose_name="Instrucciones de Yape"),
        ),
        migrations.AddField(
            model_name="saassettings",
            name="binance_holder",
            field=models.CharField(blank=True, max_length=120, verbose_name="Titular Binance"),
        ),
        migrations.AddField(
            model_name="saassettings",
            name="binance_instructions",
            field=models.TextField(blank=True, verbose_name="Instrucciones de Binance Pay"),
        ),
        migrations.AddField(
            model_name="saassettings",
            name="binance_pay_id",
            field=models.CharField(blank=True, max_length=30, verbose_name="Binance Pay ID"),
        ),
        migrations.AddField(
            model_name="saassettings",
            name="binance_qr",
            field=models.ImageField(blank=True, help_text="QR de Binance Pay para cobrar el alquiler.", upload_to="jheliz_control/binance/", verbose_name="QR de Binance Pay"),
        ),
        migrations.RunPython(move_binance_out_of_yape, migrations.RunPython.noop),
    ]
