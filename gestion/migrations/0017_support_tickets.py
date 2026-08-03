import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0016_multicurrency"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="SupportContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("telegram_chat_id", models.CharField(blank=True, db_index=True, max_length=32)),
                ("telegram_username", models.CharField(blank=True, max_length=64)),
                ("linked_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="support_contact", to="gestion.client")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jc_support_contacts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Contacto de soporte",
                "verbose_name_plural": "Contactos de soporte",
            },
        ),
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("new", "Nuevo"), ("open", "En atención"), ("waiting", "Esperando cliente"), ("resolved", "Resuelto")], default="new", max_length=12)),
                ("priority", models.CharField(choices=[("normal", "Normal"), ("urgent", "Urgente")], default="normal", max_length=10)),
                ("category", models.CharField(choices=[("access", "No puedo ingresar"), ("password", "Contraseña incorrecta"), ("blocked", "Cuenta o perfil bloqueado"), ("code", "Código de acceso"), ("device", "Pantalla o dispositivo"), ("renewal", "Renovación o vencimiento"), ("other", "Otro problema")], default="other", max_length=16)),
                ("subject", models.CharField(blank=True, max_length=160)),
                ("customer_chat_id", models.CharField(blank=True, db_index=True, max_length=32)),
                ("last_message_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_tickets", to="gestion.client")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jc_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("subscription", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to="gestion.subscription")),
            ],
            options={"ordering": ["-last_message_at"]},
        ),
        migrations.CreateModel(
            name="SupportMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender", models.CharField(choices=[("customer", "Cliente"), ("agent", "Distribuidor"), ("system", "Sistema")], max_length=10)),
                ("text", models.TextField()),
                ("telegram_message_id", models.BigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="gestion.supportticket")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="SupportCustomerSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.CharField(max_length=32, unique=True)),
                ("state", models.CharField(blank=True, max_length=48)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customer_sessions", to="gestion.supportcontact")),
            ],
        ),
        migrations.AddConstraint(model_name="supportticket", constraint=models.UniqueConstraint(fields=("owner", "number"), name="uniq_support_ticket_number")),
        migrations.AddIndex(model_name="supportticket", index=models.Index(fields=["owner", "status", "-last_message_at"], name="support_owner_status_idx")),
    ]
