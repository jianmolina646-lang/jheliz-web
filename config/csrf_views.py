"""Vista amigable para fallos de verificación CSRF.

Cuando el token CSRF de un formulario vence (página abierta mucho tiempo,
botón "atrás" del navegador, o pestaña vieja), Django por defecto responde con
una pantalla "Prohibido (403)". En vez de eso, devolvemos al usuario al mismo
formulario con un aviso para que reintente con un token fresco.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

RETRY_MESSAGE = (
    "La página expiró por seguridad. Recargamos el formulario: "
    "por favor intentá de nuevo."
)


def csrf_failure(request, reason="", template_name=""):
    """Redirige al formulario de origen con un aviso en vez del 403 de Django."""
    messages.warning(request, RETRY_MESSAGE)

    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect(request.path or "/")
