"""Middleware ligero para cabeceras que Django no maneja por defecto."""

from __future__ import annotations

from django.conf import settings

# Prefijo de URL del admin. Se evalúa una sola vez al import. Cualquier
# request cuyo path empiece con este valor recibe `X-Robots-Tag: noindex,
# nofollow` para que un crawler malicioso (o uno que llegó a una URL
# filtrada en logs) nunca la indexe en buscadores.
_ADMIN_PREFIX = "/panel-virtualidadsp/"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        permissions = getattr(settings, "PERMISSIONS_POLICY", "")
        if permissions and "Permissions-Policy" not in response.headers:
            response.headers["Permissions-Policy"] = permissions
        # Cross-Origin-Opener-Policy ya viene de Django (SecurityMiddleware), pero
        # añadimos COEP/CORP por defecto para aislar la página del admin.
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        # Defense-in-depth: nunca permitir que un buscador indexe el admin,
        # incluso si una URL termina filtrándose en logs/referers.
        if request.path.startswith(_ADMIN_PREFIX):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
        return response
