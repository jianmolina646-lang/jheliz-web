from django.db import migrations, models
import gestion.models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0018_renewal_web_flow")]
    operations = [
        migrations.AddField(
            model_name="renewalrequest", name="rejection_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="renewalrequest", name="link_expires_at",
            field=models.DateTimeField(default=gestion.models.renewal_link_expiry),
        ),
    ]
