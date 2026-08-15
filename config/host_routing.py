"""Ruteo por dominio: sirve el producto SaaS en el host de jheliztv.xyz.

Cuando el ``Host`` de la petición coincide con uno de ``JHELIZTV_HOSTS``,
cambiamos ``request.urlconf`` a ``config.urls_jheliztv`` para servir Jheliz
Control (landing + panel del inquilino). Cualquier otro host (la tienda) usa el
``ROOT_URLCONF`` por defecto, así que no se ve afectado.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class JheliztvHostMiddleware:
    PUBLIC_INDEX_PATHS = {
        "/",
        "/funciones/",
        "/precios/",
        "/como-funciona/",
        "/preguntas-frecuentes/",
        "/contacto/",
    }

    def __init__(self, get_response):
        self.get_response = get_response
        hosts = getattr(settings, "JHELIZTV_HOSTS", []) or []
        self.hosts = {h.strip().lower() for h in hosts if h.strip()}

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        if host == "www.jheliztv.xyz":
            return HttpResponsePermanentRedirect(
                f"https://jheliztv.xyz{request.get_full_path()}"
            )
        if host in self.hosts:
            request.urlconf = "config.urls_jheliztv"
            request.is_jheliztv = True
        else:
            request.is_jheliztv = False
        response = self.get_response(request)
        if request.is_jheliztv and request.path not in self.PUBLIC_INDEX_PATHS:
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
