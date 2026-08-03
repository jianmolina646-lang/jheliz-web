from django.db import migrations, models
import orders.encryption


def normalize_and_encrypt_stock(apps, schema_editor):
    StockEmail = apps.get_model("gestion", "StockEmail")
    StockEmail.objects.filter(status="sold", customer_name="").update(
        customer_name="Cliente no registrado"
    )
    for row in StockEmail.objects.exclude(password="").iterator():
        row.save(update_fields=["password"])


class Migration(migrations.Migration):
    # PostgreSQL debe confirmar la reescritura cifrada antes de crear el CHECK.
    atomic = False
    dependencies = [("gestion", "0014_stockemail_inventory")]

    operations = [
        migrations.AddField(
            model_name="stockemail",
            name="notes",
            field=models.CharField(
                blank=True, max_length=200, verbose_name="Notas"
            ),
        ),
        migrations.AlterField(
            model_name="stockemail",
            name="password",
            field=orders.encryption.EncryptedTextField(
                blank=True, verbose_name="Contraseña"
            ),
        ),
        migrations.RunPython(
            normalize_and_encrypt_stock,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="stockemail",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status="available")
                    | ~models.Q(customer_name="")
                ),
                name="sold_stock_email_requires_customer",
            ),
        ),
    ]
