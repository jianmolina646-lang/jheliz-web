from django.db import migrations, models


def number_existing_stock(apps, schema_editor):
    StockEmail = apps.get_model("gestion", "StockEmail")
    pairs = (
        StockEmail.objects.order_by()
        .values_list("owner_id", "service_id")
        .distinct()
    )
    for owner_id, service_id in pairs:
        rows = StockEmail.objects.filter(
            owner_id=owner_id, service_id=service_id
        ).order_by("created_at", "pk")
        for number, row in enumerate(rows, start=1):
            row.inventory_number = number
            row.save(update_fields=["inventory_number"])


class Migration(migrations.Migration):
    dependencies = [("gestion", "0013_whatsapp_automation")]

    operations = [
        migrations.AddField(
            model_name="stockemail",
            name="acquisition_method",
            field=models.CharField(
                blank=True, max_length=120, verbose_name="Método de adquisición"
            ),
        ),
        migrations.AddField(
            model_name="stockemail",
            name="customer_name",
            field=models.CharField(blank=True, max_length=160, verbose_name="Cliente"),
        ),
        migrations.AddField(
            model_name="stockemail",
            name="inventory_number",
            field=models.PositiveIntegerField(
                blank=True, editable=False, null=True,
                verbose_name="Número de inventario",
            ),
        ),
        migrations.RunPython(number_existing_stock, migrations.RunPython.noop),
        migrations.RemoveField(model_name="stockemail", name="notes"),
        migrations.AddConstraint(
            model_name="stockemail",
            constraint=models.UniqueConstraint(
                fields=("owner", "service", "inventory_number"),
                name="uniq_stock_number_per_owner_service",
            ),
        ),
        migrations.AlterModelOptions(
            name="stockemail",
            options={
                "ordering": ["service__name", "status", "inventory_number", "email"],
                "verbose_name": "Correo en stock",
                "verbose_name_plural": "Correos en stock",
            },
        ),
    ]
