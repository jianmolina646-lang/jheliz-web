"""Privacy-conscious usage telemetry for the Jheliz Control tenant panel."""

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from .models import Tenant, TenantActivity, TenantActivityEvent


ACTION_LABELS = {
    "/app/clientes/agregar/": "cliente_creado",
    "/app/suscripciones/agregar/": "suscripcion_creada",
    "/app/movimientos/agregar/": "movimiento_creado",
    "/app/servicios/agregar/": "servicio_creado",
    "/app/telegram/": "telegram_configurado",
    "/app/whatsapp/": "whatsapp_configurado",
}


def _action_for(path):
    if path in ACTION_LABELS:
        return ACTION_LABELS[path]
    if "/renovar/" in path:
        return "suscripcion_renovada"
    if "/editar/" in path:
        return "registro_actualizado"
    return "accion_panel"


class TenantActivityMiddleware:
    """Track presence at most once/minute and sanitized POST actions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not request.path.startswith("/app/"):
            return response
        tenant = Tenant.objects.filter(user_id=user.pk).first()
        if tenant is None:
            return response
        now = timezone.now()
        key = f"jc:activity:{tenant.pk}"
        if cache.add(key, 1, timeout=60):
            activity, created = TenantActivity.objects.get_or_create(
                tenant=tenant,
                defaults={
                    "last_seen_at": now,
                    "last_path": request.path[:160],
                    "total_requests": 1,
                    "session_count": 1,
                },
            )
            if not created:
                TenantActivity.objects.filter(pk=activity.pk).update(
                    last_seen_at=now,
                    last_path=request.path[:160],
                    total_requests=F("total_requests") + 1,
                )
        if request.method == "POST" and response.status_code < 400:
            TenantActivityEvent.objects.create(
                tenant=tenant,
                action=_action_for(request.path),
                path=request.path[:160],
            )
        return response
