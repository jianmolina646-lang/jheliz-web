from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

from blog.sitemaps import BlogPostSitemap
from catalog.seo_views import manifest_json, robots_txt
from catalog.sitemaps import SITEMAPS
from orders import media_views as orders_media_views

SITEMAPS_ALL = {**SITEMAPS, "blog": BlogPostSitemap}

urlpatterns = [
    path("jheliz-admin/", admin.site.urls),
    # SEO / PWA endpoints (root-level)
    path("robots.txt", robots_txt, name="robots_txt"),
    path("manifest.webmanifest", manifest_json, name="pwa-manifest"),
    path(
        "sitemap.xml",
        sitemap_view,
        {"sitemaps": SITEMAPS_ALL},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("cuenta/", include("accounts.urls", namespace="accounts")),
    path("pedidos/", include("orders.urls", namespace="orders")),
    path("soporte/", include("support.urls", namespace="support")),
    path("blog/", include("blog.urls", namespace="blog")),
    path("", include("catalog.urls", namespace="catalog")),
]

# ---------------------------------------------------------------------------
# Media protegida
#
# /media/payments/proofs/  -> staff-only (comprobantes Yape de los clientes)
# /media/payments/yape/    -> usuarios autenticados (QR del comerciante)
# /media/...               -> público (imágenes de productos, etc.)
#
# Importante: las rutas protegidas se declaran ANTES del catch-all público para
# que Django las matchee primero.
# ---------------------------------------------------------------------------
_media_prefix = settings.MEDIA_URL.lstrip("/").rstrip("/")
urlpatterns += [
    path(
        f"{_media_prefix}/payments/proofs/<path:path>",
        orders_media_views.serve_payment_proof,
        name="payment_proof_media",
    ),
    path(
        f"{_media_prefix}/payments/yape/<path:path>",
        orders_media_views.serve_yape_qr,
        name="payment_yape_media",
    ),
    re_path(
        rf"^{_media_prefix}/(?P<path>.*)$",
        static_serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
