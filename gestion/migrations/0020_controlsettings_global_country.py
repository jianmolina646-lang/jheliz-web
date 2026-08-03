from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0019_renewal_privacy")]
    operations = [
        migrations.AlterField(
            model_name="controlsettings", name="country",
            field=models.CharField(default="PE", max_length=2, verbose_name="País"),
        ),
    ]
