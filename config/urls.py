from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

urlpatterns = [
    path("jheliz-admin/", admin.site.urls),
    path("cuenta/", include("accounts.urls", namespace="accounts")),
    path("pedidos/", include("orders.urls", namespace="orders")),
    path("soporte/", include("support.urls", namespace="support")),
    path("", include("catalog.urls", namespace="catalog")),
]

# Media se sirve desde Django incluso en producción (volumen docker compartido).
# Para tráfico alto, nginx puede cachear /media/ por delante.
_media_prefix = settings.MEDIA_URL.lstrip("/")
urlpatterns += [
    re_path(
        rf"^{_media_prefix}(?P<path>.*)$",
        static_serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
