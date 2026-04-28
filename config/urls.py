from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

from blog.sitemaps import BlogPostSitemap
from catalog.seo_views import google_site_verification, manifest_json, robots_txt
from catalog.sitemaps import SITEMAPS
from config import admin_views
from orders import media_views as orders_media_views

SITEMAPS_ALL = {**SITEMAPS, "blog": BlogPostSitemap}

urlpatterns = [
    # Vistas extra del admin (deben ir antes de admin.site.urls).
    path("jheliz-admin/reports/", admin_views.reports_view, name="admin_reports"),
    path(
        "jheliz-admin/reports/export.csv",
        admin_views.reports_export_csv,
        name="admin_reports_export_csv",
    ),
    path(
        "jheliz-admin/top-customers/",
        admin_views.top_customers_view,
        name="admin_top_customers",
    ),
    path(
        "jheliz-admin/health/",
        admin_views.health_check_view,
        name="admin_health_check",
    ),
    path(
        "jheliz-admin/notifications/count.json",
        admin_views.notifications_count,
        name="admin_notifications_count",
    ),
    path(
        "jheliz-admin/search/",
        admin_views.global_search,
        name="admin_global_search",
    ),
    path(
        "jheliz-admin/reply-templates.json",
        admin_views.reply_templates_json,
        name="admin_reply_templates_json",
    ),
    path(
        "jheliz-admin/renewals/",
        admin_views.renewals_view,
        name="admin_renewals",
    ),
    path(
        "jheliz-admin/renewals/<int:item_id>/renew/",
        admin_views.renew_item,
        name="admin_renew_item",
    ),
    path(
        "jheliz-admin/stock/",
        admin_views.stock_overview,
        name="admin_stock_overview",
    ),
    path(
        "jheliz-admin/stock/quick-add/",
        admin_views.stock_quick_add,
        name="admin_stock_quick_add",
    ),
    path(
        "jheliz-admin/stock/<int:item_id>/action/",
        admin_views.stock_quick_action,
        name="admin_stock_quick_action",
    ),
    path(
        "jheliz-admin/customers/",
        admin_views.customer_index,
        name="admin_customer_index",
    ),
    path(
        "jheliz-admin/customers/<path:email>/",
        admin_views.customer_detail,
        name="admin_customer_detail",
    ),
    path("jheliz-admin/", admin.site.urls),
    # SEO / PWA endpoints (root-level)
    path("robots.txt", robots_txt, name="robots_txt"),
    re_path(
        r"^(?P<token>google[a-f0-9]+)\.html$",
        google_site_verification,
        name="google_site_verification",
    ),
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
