from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("jheliz-admin/", admin.site.urls),
    path("cuenta/", include("accounts.urls", namespace="accounts")),
    path("pedidos/", include("orders.urls", namespace="orders")),
    path("soporte/", include("support.urls", namespace="support")),
    path("", include("catalog.urls", namespace="catalog")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
