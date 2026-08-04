from django.db import migrations, models
from django.db.models.functions import Lower
import orders.encryption


def merge_duplicate_services(apps, schema_editor):
    Service = apps.get_model("gestion", "Service")
    Subscription = apps.get_model("gestion", "Subscription")
    StockEmail = apps.get_model("gestion", "StockEmail")
    duplicates = (
        Service.objects.values("owner_id")
        .annotate(normalized_name=Lower("name"), total=models.Count("id"))
        .filter(total__gt=1)
    )
    for group in duplicates.iterator():
        rows = list(
            Service.objects.filter(
                owner_id=group["owner_id"], name__iexact=group["normalized_name"]
            ).order_by("id")
        )
        canonical = rows[0]
        for duplicate in rows[1:]:
            Subscription.objects.filter(service_id=duplicate.id).update(service_id=canonical.id)
            StockEmail.objects.filter(service_id=duplicate.id).update(service_id=canonical.id)
            duplicate.delete()


def encrypt_subscription_secrets(apps, schema_editor):
    from orders.encryption import encrypt_text

    table = schema_editor.quote_name("gestion_subscription")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, account_password, profile_pin FROM {table}")
        rows = cursor.fetchall()
        for row_id, password, pin in rows:
            encrypted_password = encrypt_text(password) if password else ""
            encrypted_pin = encrypt_text(pin) if pin else ""
            cursor.execute(
                f"UPDATE {table} SET account_password = %s, profile_pin = %s WHERE id = %s",
                [encrypted_password, encrypted_pin, row_id],
            )


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("gestion", "0021_private_payment_proofs")]

    operations = [
        migrations.RunPython(merge_duplicate_services, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="subscription",
            name="account_password",
            field=orders.encryption.EncryptedTextField(blank=True, verbose_name="Contraseña"),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="profile_pin",
            field=orders.encryption.EncryptedTextField(blank=True, verbose_name="PIN"),
        ),
        migrations.RunPython(encrypt_subscription_secrets, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(Lower("name"), "owner", name="uniq_service_owner_name_ci"),
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["owner", "is_archived", "expires_at"], name="sub_owner_active_exp_idx"),
        ),
        migrations.AddConstraint(model_name="subscription", constraint=models.CheckConstraint(condition=models.Q(profiles__gte=1, profiles__lte=7), name="subscription_profiles_1_7")),
        migrations.AddConstraint(model_name="subscription", constraint=models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="subscription_exchange_rate_gt_0")),
        migrations.AddConstraint(model_name="subscription", constraint=models.CheckConstraint(condition=models.Q(cost__gte=0, investment__gte=0), name="subscription_amounts_nonnegative")),
        migrations.AddIndex(model_name="transaction", index=models.Index(fields=["owner", "-occurred_at"], name="tx_owner_occurred_idx")),
        migrations.AddConstraint(model_name="transaction", constraint=models.CheckConstraint(condition=models.Q(amount__gte=0, base_amount__gte=0), name="transaction_amounts_nonnegative")),
        migrations.AddConstraint(model_name="transaction", constraint=models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="transaction_exchange_rate_gt_0")),
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS pg_trgm", migrations.RunSQL.noop),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS client_name_trgm_idx ON gestion_client USING gin (name gin_trgm_ops)",
            "DROP INDEX CONCURRENTLY IF EXISTS client_name_trgm_idx",
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS client_email_trgm_idx ON gestion_client USING gin (email gin_trgm_ops)",
            "DROP INDEX CONCURRENTLY IF EXISTS client_email_trgm_idx",
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS client_whatsapp_trgm_idx ON gestion_client USING gin (whatsapp gin_trgm_ops)",
            "DROP INDEX CONCURRENTLY IF EXISTS client_whatsapp_trgm_idx",
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS client_telegram_trgm_idx ON gestion_client USING gin (telegram gin_trgm_ops)",
            "DROP INDEX CONCURRENTLY IF EXISTS client_telegram_trgm_idx",
        ),
    ]
