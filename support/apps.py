from django.apps import AppConfig


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "support"
    verbose_name = "Soporte"

    def ready(self):
        from . import signals  # noqa: F401
