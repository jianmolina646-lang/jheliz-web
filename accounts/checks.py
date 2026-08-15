"""Comprobaciones de despliegue para controles que requieren activación manual."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def production_security_flags(app_configs, **kwargs):
    warnings = []
    if not settings.DEBUG and not getattr(settings, "ADMIN_2FA_ENFORCED", False):
        warnings.append(Warning(
            "El 2FA obligatorio del administrador no está activado.",
            hint="Confirma primero un TOTP y luego configura ADMIN_2FA_ENFORCED=True.",
            id="jheliz_security.W001",
        ))
    if not settings.DEBUG and not getattr(settings, "SECURITY_EVENT_ALERTS", True):
        warnings.append(Warning(
            "Las alertas de SecurityEvent están desactivadas.",
            hint="Configura SECURITY_EVENT_ALERTS=True.",
            id="jheliz_security.W002",
        ))
    return warnings
