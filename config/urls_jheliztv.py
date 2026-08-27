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
from django.http import HttpResponseNotFound
from django.views.static import serve as static_serve
from django.views.generic import RedirectView

from gestion import seo_views


handler404 = "gestion.seo_views.page_not_found"


def _private_media(request, path=""):
    return HttpResponseNotFound()

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(
            url=f"{settings.STATIC_URL}img/favicon.ico",
            permanent=True,
        ),
        name="jheliztv_favicon",
    ),
    path("robots.txt", seo_views.robots_txt, name="jheliztv_robots"),
    path("sitemap.xml", seo_views.sitemap_xml, name="jheliztv_sitemap"),
    path("i18n/", include("django.conf.urls.i18n")),
    # Panel del dueño (solo staff): inquilinos + pagos de alquiler.
    path("control/", include("gestion.owner_urls")),
    path("", include("gestion.tenant_urls")),
]

# Media (QR de Yape, comprobantes, imágenes de servicios).
_media_prefix = settings.MEDIA_URL.lstrip("/").rstrip("/")
urlpatterns += [
    re_path(r"^media/jheliz_control/(?:pagos|renewal_proofs)/(?P<path>.*)$", _private_media),
    re_path(
        rf"^{_media_prefix}/(?P<path>.*)$",
        static_serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
