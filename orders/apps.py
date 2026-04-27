from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orders"
    verbose_name = "Pedidos"

    def ready(self) -> None:
        from . import signals  # noqa: F401
