"""Middleware ligero para cabeceras que Django no maneja por defecto."""

from __future__ import annotations

from django.conf import settings


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
        return response
