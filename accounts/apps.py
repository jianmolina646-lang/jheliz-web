from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas"

    def ready(self):
        # Aplica enforcement de 2FA en el admin si ADMIN_2FA_ENFORCED es True.
        from . import admin_2fa  # noqa: F401

        # Honeypot anti-bot en el form de login + notificación de logins
        # admin (email + Telegram). Se instala DESPUÉS de admin_2fa para que
        # el merged form herede de OTPAuthenticationForm cuando 2FA está on.
        from . import admin_security  # noqa: F401
