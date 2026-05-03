from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Cat\u00e1logo"

    def ready(self) -> None:
        from auditlog.registry import auditlog

        from . import signals  # noqa: F401  (registra receivers post_save Product)
        from .models import Plan, Product, StockItem

        # No registramos las credenciales del StockItem por ser sensibles.
        auditlog.register(StockItem, exclude_fields=["credentials"])
        auditlog.register(Product)
        auditlog.register(Plan)
