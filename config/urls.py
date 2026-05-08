from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

from blog.sitemaps import BlogPostSitemap
from catalog.seo_views import (
    google_site_verification,
    manifest_json,
    robots_txt,
    service_worker,
)
from catalog.sitemaps import SITEMAPS
from config import admin_views
from livechat import admin_views as livechat_admin_views
from orders import media_views as orders_media_views
from support import views as support_views

SITEMAPS_ALL = {**SITEMAPS, "blog": BlogPostSitemap}

urlpatterns = [
    # Vistas extra del admin (deben ir antes de admin.site.urls).
    path(
        "panel-jheliz-2026/inbox/",
        admin_views.inbox_view,
        name="admin_inbox",
    ),
    path(
        "panel-jheliz-2026/reports/charts/",
        admin_views.reports_charts_view,
        name="admin_reports_charts",
    ),
    path(
        "panel-jheliz-2026/security/2fa/",
        admin_views.admin_2fa_setup,
        name="admin_2fa_setup",
    ),
    path(
        "panel-jheliz-2026/auditoria/",
        admin_views.auditlog_view,
        name="admin_auditlog",
    ),
    path(
        "panel-jheliz-2026/auditoria/<int:pk>/",
        admin_views.auditlog_detail,
        name="admin_auditlog_detail",
    ),
    path("panel-jheliz-2026/reports/", admin_views.reports_view, name="admin_reports"),
    path(
        "panel-jheliz-2026/reports/export.csv",
        admin_views.reports_export_csv,
        name="admin_reports_export_csv",
    ),
    path(
        "panel-jheliz-2026/top-customers/",
        admin_views.top_customers_view,
        name="admin_top_customers",
    ),
    path(
        "panel-jheliz-2026/health/",
        admin_views.health_check_view,
        name="admin_health_check",
    ),
    path(
        "panel-jheliz-2026/notifications/count.json",
        admin_views.notifications_count,
        name="admin_notifications_count",
    ),
    path(
        "panel-jheliz-2026/search/",
        admin_views.global_search,
        name="admin_global_search",
    ),
    path(
        "panel-jheliz-2026/reply-templates.json",
        admin_views.reply_templates_json,
        name="admin_reply_templates_json",
    ),
    path(
        "panel-jheliz-2026/replace-blocked-account/",
        admin_views.replace_blocked_account_view,
        name="admin_replace_blocked_account",
    ),
    path(
        "panel-jheliz-2026/renewals/",
        admin_views.renewals_view,
        name="admin_renewals",
    ),
    path(
        "panel-jheliz-2026/bulk-delivery/",
        admin_views.bulk_delivery_view,
        name="admin_bulk_delivery",
    ),
    path(
        "panel-jheliz-2026/bulk-delivery/deliver/<int:order_id>/",
        admin_views.bulk_deliver_one,
        name="admin_bulk_deliver_one",
    ),
    path(
        "panel-jheliz-2026/bulk-delivery/deliver-all/",
        admin_views.bulk_deliver_all,
        name="admin_bulk_deliver_all",
    ),
    path(
        "panel-jheliz-2026/renewals/<int:item_id>/renew/",
        admin_views.renew_item,
        name="admin_renew_item",
    ),
    path(
        "panel-jheliz-2026/stock/",
        admin_views.stock_overview,
        name="admin_stock_overview",
    ),
    path(
        "panel-jheliz-2026/stock/cuentas/",
        admin_views.stock_list,
        name="admin_stock_list",
    ),
    path(
        "panel-jheliz-2026/stock/quick-add/",
        admin_views.stock_quick_add,
        name="admin_stock_quick_add",
    ),
    path(
        "panel-jheliz-2026/stock/<int:item_id>/action/",
        admin_views.stock_quick_action,
        name="admin_stock_quick_action",
    ),
    path(
        "panel-jheliz-2026/customers/",
        admin_views.customer_index,
        name="admin_customer_index",
    ),
    path(
        "panel-jheliz-2026/customers/<path:email>/",
        admin_views.customer_detail,
        name="admin_customer_detail",
    ),
    path(
        "panel-jheliz-2026/support/ticket/<int:ticket_id>/chat/",
        admin_views.support_chat_view,
        name="admin_support_chat",
    ),
    path(
        "panel-jheliz-2026/support/ticket/<int:ticket_id>/chat/reply/",
        admin_views.support_chat_reply,
        name="admin_support_chat_reply",
    ),
    path(
        "panel-jheliz-2026/support/ticket/<int:ticket_id>/chat/messages/",
        admin_views.support_chat_messages,
        name="admin_support_chat_messages",
    ),
    # ---- Live chat (cliente <-> admin) -----------------------------------
    path(
        "panel-jheliz-2026/livechat/",
        livechat_admin_views.chat_index,
        name="admin_livechat_index",
    ),
    path(
        "panel-jheliz-2026/livechat/unread-count.json",
        livechat_admin_views.chat_unread_count,
        name="admin_livechat_unread_count",
    ),
    path(
        "panel-jheliz-2026/livechat/<int:room_id>/",
        livechat_admin_views.chat_detail,
        name="admin_livechat_detail",
    ),
    path(
        "panel-jheliz-2026/livechat/<int:room_id>/reply/",
        livechat_admin_views.chat_reply,
        name="admin_livechat_reply",
    ),
    path(
        "panel-jheliz-2026/livechat/<int:room_id>/messages/",
        livechat_admin_views.chat_messages_partial,
        name="admin_livechat_messages",
    ),
    path(
        "panel-jheliz-2026/livechat/<int:room_id>/close/",
        livechat_admin_views.chat_close,
        name="admin_livechat_close",
    ),
    path(
        "panel-jheliz-2026/livechat/<int:room_id>/reopen/",
        livechat_admin_views.chat_reopen,
        name="admin_livechat_reopen",
    ),
    path("panel-jheliz-2026/", admin.site.urls),
    # SEO / PWA endpoints (root-level)
    path("robots.txt", robots_txt, name="robots_txt"),
    re_path(
        r"^(?P<token>google[a-f0-9]+)\.html$",
        google_site_verification,
        name="google_site_verification",
    ),
    path("manifest.webmanifest", manifest_json, name="pwa-manifest"),
    path("sw.js", service_worker, name="pwa-service-worker"),
    path(
        "sitemap.xml",
        sitemap_view,
        {"sitemaps": SITEMAPS_ALL},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    # Verificador de códigos (rutas públicas cortas en la raíz).
    path("codigos/", support_views.code_request_create, name="code_create"),
    path(
        "codigos/<str:token>/",
        support_views.code_request_status,
        name="code_status",
    ),
    path(
        "codigos/<str:token>/estado.json",
        support_views.code_request_status_json,
        name="code_status_json",
    ),
    path(
        "distribuidor/codigos/",
        support_views.code_request_distrib_create,
        name="code_distrib_create",
    ),
    path(
        "distribuidor/codigos/<str:token>/",
        support_views.code_request_distrib_status,
        name="code_distrib_status",
    ),
    path("cuenta/", include("accounts.urls", namespace="accounts")),
    path("pedidos/", include("orders.urls", namespace="orders")),
    path("soporte/", include("support.urls", namespace="support")),
    path("blog/", include("blog.urls", namespace="blog")),
    path("chat/", include("livechat.urls", namespace="livechat")),
    path("", include("catalog.urls", namespace="catalog")),
]

# ---------------------------------------------------------------------------
# Media protegida
#
# /media/payments/proofs/  -> staff-only (comprobantes Yape de los clientes)
# /media/payments/yape/    -> público (QR del comerciante, visible a invitados)
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
