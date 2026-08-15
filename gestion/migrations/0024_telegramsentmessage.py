from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0023_tenant_manage_permission")]

    operations = [
        migrations.CreateModel(
            name="TelegramSentMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bot_key", models.CharField(db_index=True, max_length=32)),
                ("chat_id", models.CharField(max_length=64)),
                ("message_id", models.BigIntegerField()),
                ("sent_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("-sent_at",)},
        ),
        migrations.AddConstraint(
            model_name="telegramsentmessage",
            constraint=models.UniqueConstraint(
                fields=("bot_key", "chat_id", "message_id"),
                name="uniq_telegram_sent_message",
            ),
        ),
    ]
