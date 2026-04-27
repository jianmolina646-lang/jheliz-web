from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orders"
    verbose_name = "Pedidos"

    def ready(self) -> None:
        from auditlog.registry import auditlog

        from . import signals  # noqa: F401
        from .models import Order, OrderItem, PaymentSettings

        # Excluir credenciales del log: no queremos guardar el "antes" y el
        # "después" de un texto sensible en otra tabla.
        auditlog.register(
            OrderItem,
            exclude_fields=["delivered_credentials"],
        )
        auditlog.register(Order)
        auditlog.register(PaymentSettings)
