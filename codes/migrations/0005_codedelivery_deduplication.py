from django.db import migrations, models


def add_missing_delivery_columns(apps, schema_editor):
    """Keep the migration safe for databases where these columns already exist."""
    delivery_model = apps.get_model("codes", "CodeDelivery")
    table_name = delivery_model._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        existing = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    quote = schema_editor.quote_name
    table = quote(table_name)
    if "payload_fingerprint" not in existing:
        schema_editor.execute(
            f"ALTER TABLE {table} ADD COLUMN {quote('payload_fingerprint')} varchar(64) NOT NULL DEFAULT ''"
        )
    if "duplicate" not in existing:
        schema_editor.execute(
            f"ALTER TABLE {table} ADD COLUMN {quote('duplicate')} boolean NOT NULL DEFAULT false"
        )
    schema_editor.execute(
        f"CREATE INDEX IF NOT EXISTS {quote('codes_codedelivery_payload_fingerprint_idx')} "
        f"ON {table} ({quote('payload_fingerprint')})"
    )


class Migration(migrations.Migration):
    dependencies = [("codes", "0004_botstate_daily_limit")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_missing_delivery_columns, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="codedelivery",
                    name="payload_fingerprint",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        verbose_name="Huella del resultado",
                    ),
                ),
                migrations.AddField(
                    model_name="codedelivery",
                    name="duplicate",
                    field=models.BooleanField(default=False, verbose_name="Resultado repetido"),
                ),
            ],
        ),
    ]
