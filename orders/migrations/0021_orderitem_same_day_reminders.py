from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0020_enable_binance_and_bank"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="expiry_reminder_7d_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="expiry_reminder_0d_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="distri_reminder_0d_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
