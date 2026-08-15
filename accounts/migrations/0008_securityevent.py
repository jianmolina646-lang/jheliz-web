from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_alter_walletrecharge_method")]
    operations = [
        migrations.CreateModel(
            name="SecurityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=80)),
                ("severity", models.CharField(choices=[("info", "Informativo"), ("warning", "Advertencia"), ("critical", "Crítico")], db_index=True, default="info", max_length=10)),
                ("username", models.CharField(blank=True, db_index=True, max_length=254)),
                ("ip_address", models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("path", models.CharField(blank=True, max_length=500)),
                ("request_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(model_name="securityevent", index=models.Index(fields=["event_type", "-created_at"], name="security_type_time_idx")),
    ]
