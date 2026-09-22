from django.db import migrations

import orders.encryption


class Migration(migrations.Migration):
    dependencies = [("catalog", "0022_alter_sitesettings_seo_meta_description_and_more")]

    operations = [
        migrations.AlterField(
            model_name="stockitem",
            name="credentials",
            field=orders.encryption.EncryptedTextField(
                help_text=(
                    "Texto libre que recibirá el cliente. Ej:\n"
                    "Correo: foo@bar.com\nContraseña: 1234\nPerfil: Perfil 2\nPIN: 0000"
                ),
                verbose_name="Credenciales",
            ),
        ),
    ]
