"""URLconf raíz para el dominio del producto SaaS **jheliztv.xyz**.

Cuando una visita entra por ese dominio, el middleware ``JheliztvHostMiddleware``
apunta ``request.urlconf`` a este módulo, de modo que se sirve **solo** Jheliz
Control (landing + login + panel del inquilino + cobro Yape). La tienda
(`ecormecejhelizstore.com`) sigue usando ``config.urls`` sin cambios.

El proveedor (vos) aprueba los pagos desde el admin de la tienda
(`/panel-jheliz-2026/` → "Pagos de alquiler").
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("gestion.tenant_urls")),
]

# Media (QR de Yape, comprobantes, imágenes de servicios).
_media_prefix = settings.MEDIA_URL.lstrip("/").rstrip("/")
urlpatterns += [
    re_path(
        rf"^{_media_prefix}/(?P<path>.*)$",
        static_serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
