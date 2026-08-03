from decimal import Decimal

from django.db import migrations, models


CURRENCIES = [
    ("PEN", "PEN · Sol peruano (S/)"), ("CLP", "CLP · Peso chileno ($)"),
    ("MXN", "MXN · Peso mexicano ($)"), ("USD", "USD · Dólar estadounidense (US$)"),
    ("USDT", "USDT · Tether (USDT)"), ("COP", "COP · Peso colombiano ($)"),
    ("ARS", "ARS · Peso argentino ($)"), ("BRL", "BRL · Real brasileño (R$)"),
    ("BOB", "BOB · Boliviano (Bs.)"), ("EUR", "EUR · Euro (€)"),
]


def migrate_money(apps, schema_editor):
    Subscription = apps.get_model("gestion", "Subscription")
    Transaction = apps.get_model("gestion", "Transaction")
    ControlSettings = apps.get_model("gestion", "ControlSettings")
    for model in (Subscription, Transaction, ControlSettings):
        model.objects.filter(currency="S/").update(currency="PEN")
    for tx in Transaction.objects.all().iterator():
        tx.base_currency = tx.currency if tx.currency in dict(CURRENCIES) else "PEN"
        tx.base_amount = tx.amount
        tx.exchange_rate = Decimal("1")
        tx.save(update_fields=["base_currency", "base_amount", "exchange_rate"])


class Migration(migrations.Migration):
    dependencies = [("gestion", "0015_stockemail_security")]
    operations = [
        migrations.AddField(
            model_name="controlsettings", name="country",
            field=models.CharField(choices=[("PE", "Perú"), ("CL", "Chile"), ("MX", "México"), ("US", "Estados Unidos"), ("CO", "Colombia"), ("AR", "Argentina"), ("BR", "Brasil"), ("BO", "Bolivia"), ("EC", "Ecuador"), ("OT", "Otro país")], default="PE", max_length=2, verbose_name="País"),
        ),
        migrations.AlterField(model_name="controlsettings", name="currency", field=models.CharField(choices=CURRENCIES, default="PEN", max_length=8, verbose_name="Moneda principal")),
        migrations.AlterField(model_name="subscription", name="currency", field=models.CharField(choices=CURRENCIES, default="PEN", max_length=8, verbose_name="Moneda")),
        migrations.AddField(model_name="subscription", name="exchange_rate", field=models.DecimalField(decimal_places=8, default=Decimal("1"), max_digits=18, verbose_name="Tipo de cambio a moneda principal")),
        migrations.AlterField(model_name="transaction", name="currency", field=models.CharField(choices=CURRENCIES, default="PEN", max_length=8, verbose_name="Moneda original")),
        migrations.AddField(model_name="transaction", name="base_currency", field=models.CharField(choices=CURRENCIES, default="PEN", max_length=8, verbose_name="Moneda principal al registrar")),
        migrations.AddField(model_name="transaction", name="base_amount", field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18, verbose_name="Monto convertido")),
        migrations.AddField(model_name="transaction", name="exchange_rate", field=models.DecimalField(decimal_places=8, default=Decimal("1"), help_text="Cuánto vale 1 unidad de la moneda original en la moneda principal.", max_digits=18, verbose_name="Tipo de cambio")),
        migrations.RunPython(migrate_money, migrations.RunPython.noop),
    ]
