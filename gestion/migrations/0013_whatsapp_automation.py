from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import orders.encryption


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0012_telegram_bot_sessions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="whatsapp_opt_in_at",
            field=models.DateTimeField(blank=True, help_text="Fecha en que el cliente acepto recibir recordatorios.", null=True, verbose_name="Autorizacion para avisos por WhatsApp"),
        ),
        migrations.CreateModel(
            name="WhatsAppConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("access_token", orders.encryption.EncryptedTextField(blank=True)),
                ("waba_id", models.CharField(blank=True, db_index=True, max_length=40)),
                ("phone_number_id", models.CharField(blank=True, max_length=40, null=True, unique=True)),
                ("display_phone_number", models.CharField(blank=True, max_length=40)),
                ("verified_name", models.CharField(blank=True, max_length=160)),
                ("status", models.CharField(choices=[("pending", "Pendiente"), ("active", "Activo"), ("error", "Con error"), ("disconnected", "Desconectado")], default="pending", max_length=16)),
                ("is_enabled", models.BooleanField(default=True)),
                ("template_name", models.CharField(default="recordatorio_vencimiento", max_length=128)),
                ("template_language", models.CharField(default="es", max_length=16)),
                ("reminder_days", models.JSONField(blank=True, default=list)),
                ("last_error", models.TextField(blank=True)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="jc_whatsapp_connection", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="WhatsAppReminderDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expiry_date", models.DateField()),
                ("reminder_days", models.PositiveSmallIntegerField(default=1)),
                ("recipient", models.CharField(max_length=40)),
                ("template_name", models.CharField(max_length=128)),
                ("meta_message_id", models.CharField(blank=True, db_index=True, max_length=160)),
                ("status", models.CharField(choices=[("queued", "En cola"), ("sent", "Enviado"), ("delivered", "Entregado"), ("read", "Leido"), ("failed", "Fallido")], default="queued", max_length=16)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jc_whatsapp_deliveries", to=settings.AUTH_USER_MODEL)),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_deliveries", to="gestion.subscription")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("subscription", "expiry_date", "reminder_days"), name="uniq_whatsapp_reminder_cycle"),
                ],
            },
        ),
    ]
