from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("gestion", "0011_telegramconnection"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(blank=True, max_length=48)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("menu_message_id", models.BigIntegerField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session",
                        to="gestion.telegramconnection",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sesión de Telegram",
                "verbose_name_plural": "Sesiones de Telegram",
            },
        ),
        migrations.CreateModel(
            name="TelegramActionReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=80)),
                ("action", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jc_telegram_action_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="telegramactionreceipt",
            constraint=models.UniqueConstraint(
                fields=("owner", "key"),
                name="uniq_telegram_action_per_owner",
            ),
        ),
        migrations.AddIndex(
            model_name="telegramactionreceipt",
            index=models.Index(
                fields=["created_at"],
                name="telegram_action_created_idx",
            ),
        ),
    ]
