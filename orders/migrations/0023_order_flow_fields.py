from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0022_database_hardening")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="flow_order",
            field=models.BigIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="flow_token",
            field=models.CharField(blank=True, editable=False, max_length=160, null=True, unique=True),
        ),
    ]
