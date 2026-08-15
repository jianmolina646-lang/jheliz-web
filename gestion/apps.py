from django.apps import AppConfig


class GestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestion"
    verbose_name = "Jheliz Control"

    def ready(self) -> None:
        from auditlog.registry import auditlog

        from .models import ControlSettings, SaasSettings, Subscription, Tenant, TenantPayment, Transaction

        # No auditar credenciales cifradas ni comprobantes; sí estados y finanzas.
        auditlog.register(Subscription, exclude_fields=["account_password", "profile_pin"])
        auditlog.register(Transaction)
        auditlog.register(ControlSettings)
        auditlog.register(Tenant)
        auditlog.register(TenantPayment, exclude_fields=["proof"])
        auditlog.register(SaasSettings, exclude_fields=["yape_qr"])
