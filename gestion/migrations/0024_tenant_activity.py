from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("gestion", "0023_tenant_manage_permission")]

    operations = [
        migrations.CreateModel(
            name="TenantActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(db_index=True)),
                ("last_path", models.CharField(blank=True, max_length=160)),
                ("total_requests", models.PositiveBigIntegerField(default=0)),
                ("session_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="activity", to="gestion.tenant")),
            ],
            options={"verbose_name": "Actividad de inquilino", "verbose_name_plural": "Actividad de inquilinos"},
        ),
        migrations.CreateModel(
            name="TenantActivityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(db_index=True, max_length=60)),
                ("path", models.CharField(blank=True, max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_events", to="gestion.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="tenantactivityevent",
            index=models.Index(fields=["tenant", "-created_at"], name="gestion_act_tenant_created_idx"),
        ),
    ]
