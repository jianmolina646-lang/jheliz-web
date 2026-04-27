"""
Django settings for Jheliz.
"""

from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost,jhelizservicestv.xyz,www.jhelizservicestv.xyz",
    cast=Csv(),
)
SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")

CSRF_TRUSTED_ORIGINS = [
    "https://jhelizservicestv.xyz",
    "https://www.jhelizservicestv.xyz",
]

INSTALLED_APPS = [
    # Unfold debe ir ANTES de django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    # Third-party
    "widget_tweaks",
    "django_htmx",
    "axes",  # protección anti fuerza-bruta en el login
    "django_otp",  # base para 2FA
    "django_otp.plugins.otp_totp",  # TOTP (Google Authenticator / Authy / 1Password)
    "django_otp.plugins.otp_static",  # códigos de respaldo
    "auditlog",  # registro de cambios (quién hizo qué, cuándo)
    "csp",  # Content Security Policy
    "import_export",  # CSV/XLSX import-export en el admin
    # Local
    "accounts.apps.AccountsConfig",
    "catalog.apps.CatalogConfig",
    "orders.apps.OrdersConfig",
    "support.apps.SupportConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # django-otp debe ir DESPUÉS de AuthenticationMiddleware.
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # auditlog: capture el usuario que hace cada cambio en los modelos rastreados.
    "auditlog.middleware.AuditlogMiddleware",
    "csp.middleware.CSPMiddleware",
    "config.security_headers.SecurityHeadersMiddleware",  # Permissions-Policy
    # AxesMiddleware debe ir al final, después del de auth.
    "axes.middleware.AxesMiddleware",
]

# ---- Auth backends -------------------------------------------------------
# AxesStandaloneBackend va PRIMERO para que pueda bloquear antes de validar.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Custom user with roles (cliente / distribuidor / admin)
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "catalog:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Localization: Peru
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# Currency (used across the app)
DEFAULT_CURRENCY = "PEN"
DEFAULT_CURRENCY_SYMBOL = "S/"

# Static & media
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Jheliz <no-reply@jhelizservicestv.xyz>")
SUPPORT_ADMIN_EMAIL = config("SUPPORT_ADMIN_EMAIL", default="")

# SMTP (opcional, para enviar correos reales en prod)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

# Mercado Pago
MERCADOPAGO_ACCESS_TOKEN = config("MERCADOPAGO_ACCESS_TOKEN", default="")
MERCADOPAGO_PUBLIC_KEY = config("MERCADOPAGO_PUBLIC_KEY", default="")
MERCADOPAGO_WEBHOOK_SECRET = config("MERCADOPAGO_WEBHOOK_SECRET", default="")

# Contact
WHATSAPP_NUMBER = config("WHATSAPP_NUMBER", default="+51999999999")
TELEGRAM_USERNAME = config("TELEGRAM_USERNAME", default="jhelizbot")

# Telegram bot (opcional)
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_ADMIN_CHAT_ID = config("TELEGRAM_ADMIN_CHAT_ID", default="")

# Brand
SITE_NAME = "Jheliz"
SITE_TAGLINE = "Streaming y licencias al mejor precio"

# Unfold admin theme
UNFOLD = {
    "SITE_TITLE": "Jheliz Admin",
    "SITE_HEADER": "Jheliz",
    "SITE_SUBHEADER": "Panel de administración",
    "SITE_SYMBOL": "storefront",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": "dark",
    "BORDER_RADIUS": "8px",
    "COLORS": {
        "primary": {
            "50": "253 244 255",
            "100": "250 232 255",
            "200": "245 208 254",
            "300": "240 171 252",
            "400": "232 121 249",
            "500": "217 70 239",
            "600": "192 38 211",
            "700": "162 28 175",
            "800": "134 25 143",
            "900": "112 26 117",
            "950": "74 4 78",
        },
    },
    "DASHBOARD_CALLBACK": "config.admin_dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Resumen",
                "separator": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "/jheliz-admin/",
                    },
                    {
                        "title": "Ver tienda",
                        "icon": "public",
                        "link": "/",
                    },
                ],
            },
            {
                "title": "Ventas (cliente final)",
                "separator": True,
                "items": [
                    {
                        "title": "Pedidos",
                        "icon": "receipt_long",
                        "link": "/jheliz-admin/orders/order/",
                    },
                    {
                        "title": "Items de pedidos",
                        "icon": "list_alt",
                        "link": "/jheliz-admin/orders/orderitem/",
                    },
                    {
                        "title": "Config. de pagos (Yape)",
                        "icon": "qr_code_2",
                        "link": "/jheliz-admin/orders/paymentsettings/",
                    },
                ],
            },
            {
                "title": "Catálogo",
                "separator": True,
                "items": [
                    {
                        "title": "Productos",
                        "icon": "inventory_2",
                        "link": "/jheliz-admin/catalog/product/",
                    },
                    {
                        "title": "Planes — Cliente final",
                        "icon": "sell",
                        "link": "/jheliz-admin/catalog/customerplan/",
                    },
                    {
                        "title": "Planes — Distribuidor",
                        "icon": "storefront",
                        "link": "/jheliz-admin/catalog/distributorplan/",
                    },
                    {
                        "title": "Planes (todos)",
                        "icon": "list",
                        "link": "/jheliz-admin/catalog/plan/",
                    },
                    {
                        "title": "Categorías",
                        "icon": "category",
                        "link": "/jheliz-admin/catalog/category/",
                    },
                    {
                        "title": "Stock",
                        "icon": "inventory",
                        "link": "/jheliz-admin/catalog/stockitem/",
                    },
                    {
                        "title": "Reseñas",
                        "icon": "reviews",
                        "link": "/jheliz-admin/catalog/testimonial/",
                    },
                ],
            },
            {
                "title": "Distribuidor",
                "separator": True,
                "items": [
                    {
                        "title": "Pedidos mayoristas",
                        "icon": "local_shipping",
                        "link": "/jheliz-admin/orders/distributororder/",
                    },
                    {
                        "title": "Distribuidores",
                        "icon": "badge",
                        "link": "/jheliz-admin/accounts/distributor/",
                    },
                    {
                        "title": "Movimientos de wallet",
                        "icon": "account_balance_wallet",
                        "link": "/jheliz-admin/accounts/wallettransaction/",
                    },
                ],
            },
            {
                "title": "Clientes",
                "separator": True,
                "items": [
                    {
                        "title": "Clientes",
                        "icon": "person",
                        "link": "/jheliz-admin/accounts/customer/",
                    },
                    {
                        "title": "Usuarios (staff)",
                        "icon": "group",
                        "link": "/jheliz-admin/accounts/user/",
                    },
                ],
            },
            {
                "title": "Soporte",
                "separator": True,
                "items": [
                    {
                        "title": "Tickets",
                        "icon": "support_agent",
                        "link": "/jheliz-admin/support/ticket/",
                    },
                ],
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Cifrado de datos sensibles en reposo
#
# Se usa para EncryptedTextField en orders.models.OrderItem.delivered_credentials.
# Generar con:  python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# Si no se configura en DEBUG, se deriva de SECRET_KEY (sólo dev).
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY", default="")

# ---------------------------------------------------------------------------
# django-axes: bloqueo por intentos fallidos de login
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME = config("AXES_COOLOFF_TIME_HOURS", default=1, cast=int)  # horas
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = None  # usa el formulario default con mensaje de error
AXES_VERBOSE = False

# ---------------------------------------------------------------------------
# 2FA (django-otp)
#
# El stack queda instalado pero el ENFORCEMENT (rechazar logins sin TOTP)
# se activa con ADMIN_2FA_ENFORCED=True una vez que tengas tu dispositivo
# TOTP registrado. Pasos (después de desplegar este PR):
#   1) Entra al admin con tu superuser actual.
#   2) Sección "TOTP devices" → "Añadir TOTP device" y escanea el QR con
#      Google Authenticator / Authy / 1Password.
#   3) Verifica que puedes usar el código (genera otro y entra de nuevo).
#   4) En tu .env de producción pon: ADMIN_2FA_ENFORCED=True
#      Esto fuerza que TODO superuser use TOTP. Si pierdes acceso, usa
#      `python manage.py addstatictoken <usuario>` para emitir un token
#      temporal de rescate por SSH.
# ---------------------------------------------------------------------------
ADMIN_2FA_ENFORCED = config("ADMIN_2FA_ENFORCED", default=False, cast=bool)
OTP_TOTP_ISSUER = "Jheliz Admin"

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Content Security Policy. Bloquea scripts/estilos/imágenes de orígenes
# que no estén en self. 'unsafe-inline' se mantiene en script/style por
# compatibilidad con el admin de Django/Unfold y con los bloques inline de
# las plantillas. 'unsafe-eval' es necesario para Alpine.js (lo usa Unfold
# para renderizar el sidebar, modales, etc. evaluando expresiones x-data,
# x-show, x-on con el constructor Function()).
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        # 'unsafe-eval' lo necesita Alpine.js (Unfold).
        # cdn.tailwindcss.com y unpkg.com los usa la tienda pública para Tailwind+htmx.
        "script-src": (
            "'self'",
            "'unsafe-inline'",
            "'unsafe-eval'",
            "https://cdn.tailwindcss.com",
            "https://unpkg.com",
        ),
        "style-src": (
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
        ),
        "font-src": ("'self'", "data:", "https://fonts.gstatic.com"),
        "img-src": ("'self'", "data:", "https:"),
        # Tailwind CDN hace fetch de su CSS dinámicamente; htmx hace requests al backend.
        "connect-src": ("'self'", "https://cdn.tailwindcss.com"),
        "frame-ancestors": ("'none'",),
        "base-uri": ("'self'",),
        "form-action": ("'self'",),
        "object-src": ("'none'",),
        "upgrade-insecure-requests": (),
    },
}

# Permissions-Policy (cabecera moderna que reemplaza a Feature-Policy).
# Bloqueamos APIs sensibles que el admin no necesita. Sólo incluimos
# features actualmente soportadas por Chromium para evitar warnings.
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "keyboard-map=(), magnetometer=(), microphone=(), midi=(), "
    "payment=(), picture-in-picture=(), publickey-credentials-get=(), "
    "screen-wake-lock=(), sync-xhr=(), usb=(), xr-spatial-tracking=()"
)

# ---------------------------------------------------------------------------
# Security in prod
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS: 1 año + preload (cumple requisitos de hstspreload.org).
    # Sólo activa preload una vez que estés 100% seguro de que TODOS los
    # subdominios sirven HTTPS. Sacar HSTS preload requiere meses de espera.
    SECURE_HSTS_SECONDS = config(
        "SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365, cast=int
    )
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
