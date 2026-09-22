"""Production settings for the private distributor storefront."""

from .settings import *  # noqa: F403


ROOT_URLCONF = "config.urls"
SITE_URL = "https://marketingjhelizxyz.online"
SITE_NAME = "Jheliz Distribuidores"
MARKETING_STORE_ENABLED = True

ALLOWED_HOSTS = [
    "marketingjhelizxyz.online",
    "www.marketingjhelizxyz.online",
    "localhost",
    "127.0.0.1",
]
MARKETING_HOSTS = [
    "marketingjhelizxyz.online",
    "www.marketingjhelizxyz.online",
]
JHELIZTV_HOSTS = []
CSRF_TRUSTED_ORIGINS = [
    "https://marketingjhelizxyz.online",
    "https://www.marketingjhelizxyz.online",
]

DEFAULT_FROM_EMAIL = "Jheliz Distribuidores <no-reply@marketingjhelizxyz.online>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
OTP_TOTP_ISSUER = "Jheliz Distribuidores"

# This service has its own admin navigation; other domains retain theirs.
from django.contrib.staticfiles.storage import staticfiles_storage

UNFOLD = {
    **UNFOLD,
    "SITE_TITLE": "Jheliz Mayoristas · Administración",
    "SITE_HEADER": "Jheliz Mayoristas",
    "SITE_SUBHEADER": "Venta de cuentas completas",
    "SITE_SYMBOL": "inventory_2",
    "STYLES": [*UNFOLD["STYLES"], lambda request: staticfiles_storage.url("admin/marketing-admin.css")],
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {"title": "GESTIÓN COMERCIAL", "items": [
                {"title": "Resumen", "icon": "dashboard", "link": "/panel-jheliz-control/"},
                {"title": "Pedidos", "icon": "shopping_bag", "link": "/panel-jheliz-control/orders/order/"},
                {"title": "Clientes", "icon": "groups", "link": "/panel-jheliz-control/accounts/user/"},
            ]},
            {"title": "CATÁLOGO E INVENTARIO", "separator": True, "items": [
                {"title": "Cuentas completas", "icon": "inventory_2", "link": "/panel-jheliz-control/catalog/product/?mode__exact=completa"},
                {"title": "Precios", "icon": "sell", "link": "/panel-jheliz-control/catalog/customerplan/"},
                {"title": "Stock de cuentas", "icon": "key", "link": "/panel-jheliz-control/catalog/stockitem/"},
                {"title": "Servicios y categorías", "icon": "category", "link": "/panel-jheliz-control/catalog/category/"},
            ]},
            {"title": "ATENCIÓN Y CONTROL", "separator": True, "items": [
                {"title": "Solicitudes de soporte", "icon": "support_agent", "link": "/panel-jheliz-control/support/ticket/"},
                {"title": "Reportes de ventas", "icon": "monitoring", "link": "/panel-jheliz-control/reports/"},
                {"title": "Seguridad de acceso", "icon": "verified_user", "link": "/panel-jheliz-control/security/2fa/"},
                {"title": "Abrir tienda", "icon": "storefront", "link": "/productos/"},
            ]},
        ],
    },
}
