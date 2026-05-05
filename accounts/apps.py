from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas"

    def ready(self):
        # Aplica enforcement de 2FA en el admin si ADMIN_2FA_ENFORCED es True.
        from . import admin_2fa  # noqa: F401

        # Conecta alertas de seguridad a Telegram (lockouts, login fallidos,
        # webhook MP inválido, etc.). Si Telegram no está configurado, los
        # handlers son no-op.
        from . import security_alerts
        security_alerts._connect_signals()
