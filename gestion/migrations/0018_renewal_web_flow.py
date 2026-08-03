import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0017_support_tickets"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ResellerPaymentMethod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("yape", "Yape"), ("plin", "Plin"), ("bank", "Transferencia bancaria"), ("usdt", "USDT"), ("paypal", "PayPal"), ("zelle", "Zelle"), ("mercadopago", "Mercado Pago"), ("other", "Otro")], max_length=16)),
                ("label", models.CharField(max_length=80)),
                ("holder", models.CharField(blank=True, max_length=120)),
                ("details", models.TextField(help_text="Número, cuenta, wallet o instrucciones de pago.")),
                ("qr_image", models.ImageField(blank=True, null=True, upload_to="jheliz_control/payment_methods/")),
                ("is_active", models.BooleanField(default=True)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jc_payment_methods", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["order", "label"]},
        ),
        migrations.CreateModel(
            name="RenewalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("expiry_date", models.DateField()),
                ("status", models.CharField(choices=[("invited", "Enlace enviado"), ("declined", "No renovará"), ("payment_pending", "Esperando pago"), ("proof_sent", "Pago por verificar"), ("approved", "Aprobado"), ("rejected", "Rechazado"), ("help", "Necesita ayuda")], default="invited", max_length=24)),
                ("proof", models.ImageField(blank=True, null=True, upload_to="jheliz_control/renewal_proofs/")),
                ("customer_note", models.CharField(blank=True, max_length=500)),
                ("requested_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jc_renewal_requests", to=settings.AUTH_USER_MODEL)),
                ("payment_method", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="renewal_requests", to="gestion.resellerpaymentmethod")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="renewal_requests", to="gestion.subscription")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(model_name="renewalrequest", constraint=models.UniqueConstraint(fields=("subscription", "expiry_date"), name="uniq_renewal_request_cycle")),
    ]
