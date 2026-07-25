from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0010_stockemail"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="TelegramConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.CharField(blank=True, max_length=32, null=True, unique=True)),
                ("telegram_username", models.CharField(blank=True, max_length=64)),
                ("link_token_digest", models.CharField(blank=True, max_length=64)),
                ("link_expires_at", models.DateTimeField(blank=True, null=True)),
                ("is_enabled", models.BooleanField(default=True)),
                ("notify_windows", models.JSONField(blank=True, default=list)),
                ("last_digest_date", models.DateField(blank=True, null=True)),
                ("linked_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="jc_telegram_connection", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Telegram de revendedor", "verbose_name_plural": "Telegram de revendedores"},
        ),
    ]
