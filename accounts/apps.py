from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas"

    def ready(self):
        # Aplica enforcement de 2FA en el admin si ADMIN_2FA_ENFORCED es True.
        from . import admin_2fa  # noqa: F401
