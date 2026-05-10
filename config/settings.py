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
    default="127.0.0.1,localhost,ecormecejhelizstore.com,www.ecormecejhelizstore.com",
    cast=Csv(),
)
SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")

# URL base del panel admin. Cambiá esto en .env para "esconder" el admin
# de bots que escanean rutas conocidas (/admin/, /wp-admin/, etc.). El
# valor NO debe llevar barras al inicio o al final.
ADMIN_URL_PATH = config("ADMIN_URL_PATH", default="panel-jheliz-2026").strip("/")

CSRF_TRUSTED_ORIGINS = [
    "https://ecormecejhelizstore.com",
    "https://www.ecormecejhelizstore.com",
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
    "blog.apps.BlogConfig",
    "livechat.apps.LivechatConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # i18n: detecta el idioma del usuario (cookie / header / sesión).
    "django.middleware.locale.LocaleMiddleware",
    # multi-país: inyecta `request.country` con el dict del país activo.
    "config.i18n_country.CountryMiddleware",
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
                "django.template.context_processors.i18n",
                "catalog.context_processors.site_context",
                "config.i18n_country.country_context",
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

# Localization: Peru por default (multi-país habilitado).
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# Idiomas soportados. El switcher del header expone exactamente estos.
LANGUAGES = [
    ("es", "Español"),
    ("en", "English"),
    ("pt", "Português"),
]
# Carpeta donde viven los .po/.mo de las traducciones.
LOCALE_PATHS = [BASE_DIR / "locale"]

# Currency (default cuando no se conoce el país del visitante).
DEFAULT_CURRENCY = "PEN"
DEFAULT_CURRENCY_SYMBOL = "S/"

# Países soportados. Cada uno define su moneda, su flag emoji y su locale
# preferido. El selector se renderiza en el footer; las páginas pueden
# resolver `request.country` (vía middleware liviano) para decidir cosas
# como el método de pago default o el formato de número telefónico.
COUNTRIES = [
    {"code": "PE", "name": "Perú", "flag": "🇵🇪", "currency": "PEN", "symbol": "S/", "locale": "es", "phone_cc": "+51"},
    {"code": "CO", "name": "Colombia", "flag": "🇨🇴", "currency": "COP", "symbol": "$", "locale": "es", "phone_cc": "+57"},
    {"code": "MX", "name": "México", "flag": "🇲🇽", "currency": "MXN", "symbol": "$", "locale": "es", "phone_cc": "+52"},
    {"code": "AR", "name": "Argentina", "flag": "🇦🇷", "currency": "ARS", "symbol": "$", "locale": "es", "phone_cc": "+54"},
    {"code": "CL", "name": "Chile", "flag": "🇨🇱", "currency": "CLP", "symbol": "$", "locale": "es", "phone_cc": "+56"},
    {"code": "EC", "name": "Ecuador", "flag": "🇪🇨", "currency": "USD", "symbol": "$", "locale": "es", "phone_cc": "+593"},
    {"code": "BO", "name": "Bolivia", "flag": "🇧🇴", "currency": "BOB", "symbol": "Bs.", "locale": "es", "phone_cc": "+591"},
    {"code": "BR", "name": "Brasil", "flag": "🇧🇷", "currency": "BRL", "symbol": "R$", "locale": "pt", "phone_cc": "+55"},
    {"code": "US", "name": "USA", "flag": "🇺🇸", "currency": "USD", "symbol": "$", "locale": "en", "phone_cc": "+1"},
]
DEFAULT_COUNTRY = "PE"

# Static & media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Django ≥4.2 reemplaza STATICFILES_STORAGE por la dict STORAGES. En Django 5
# el legacy STATICFILES_STORAGE es ignorado silenciosamente cuando STORAGES no
# está definido (Django usa el default StaticFilesStorage sin manifiesto). Por
# eso definimos STORAGES explícitamente para activar Whitenoise + manifiesto +
# hashing de filenames (cache busting).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Jheliz <no-reply@ecormecejhelizstore.com>")
SUPPORT_ADMIN_EMAIL = config("SUPPORT_ADMIN_EMAIL", default="")

# SMTP (opcional, para enviar correos reales en prod)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

# Password reset: token de 24h en lugar del default de 3 días.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Mercado Pago
MERCADOPAGO_ACCESS_TOKEN = config("MERCADOPAGO_ACCESS_TOKEN", default="")
MERCADOPAGO_PUBLIC_KEY = config("MERCADOPAGO_PUBLIC_KEY", default="")
MERCADOPAGO_WEBHOOK_SECRET = config("MERCADOPAGO_WEBHOOK_SECRET", default="")

# Web Push notifications (VAPID).
# Para generar el par de claves:
#   from py_vapid import Vapid
#   v = Vapid()
#   v.generate_keys()
#   v.save_key("vapid_private.pem")
#   v.save_public_key("vapid_public.pem")
#   v.public_key  # Base64URL — esto va en VAPID_PUBLIC_KEY (lo lee el browser)
# La privada va en VAPID_PRIVATE_KEY como PEM o como base64url de la EC raw.
VAPID_PUBLIC_KEY = config("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = config("VAPID_PRIVATE_KEY", default="")
VAPID_CLAIM_EMAIL = config(
    "VAPID_CLAIM_EMAIL",
    default="mailto:soporte@ecormecejhelizstore.com",
)

# Contact
WHATSAPP_NUMBER = config("WHATSAPP_NUMBER", default="+51999999999")
TELEGRAM_USERNAME = config("TELEGRAM_USERNAME", default="jhelizbot")

# Telegram bot (opcional)
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_ADMIN_CHAT_ID = config("TELEGRAM_ADMIN_CHAT_ID", default="")
# Token secreto que viaja en el header del webhook de Telegram
# (X-Telegram-Bot-Api-Secret-Token). Si está vacío, el webhook se deshabilita.
TELEGRAM_WEBHOOK_SECRET = config("TELEGRAM_WEBHOOK_SECRET", default="")
# Canal público de avisos para distribuidores (ej. "@jhelizservicetv" o
# "-1003689345000"). Si está vacío, las publicaciones automáticas a
# distribuidores se desactivan.
TELEGRAM_CHANNEL_ID = config("TELEGRAM_CHANNEL_ID", default="")
# Canal público de avisos para clientes finales (ej. "@jheliztvavisos").
# Si está vacío, las publicaciones automáticas a cliente final se
# desactivan, pero las del canal distribuidor siguen funcionando.
TELEGRAM_CUSTOMER_CHANNEL_ID = config("TELEGRAM_CUSTOMER_CHANNEL_ID", default="")

# Brand
SITE_NAME = "Jheliz"
SITE_TAGLINE = "Netflix, Disney+ y Office en Perú desde S/ 7"

def _hashed_static(path: str) -> str:
    """Devuelve la URL de un static asset con hash de manifiesto si existe.

    Equivalente a `{% static path %}` en templates. Lo usamos en los lambdas
    de Unfold STYLES/SCRIPTS para que cada deploy con cambios en el CSS/JS
    custom genere una URL nueva (ej. `admin/jheliz_polish.abc123.css`),
    obligando a los browsers a refetchear y bypassear su cache de 1 año.
    """
    from django.contrib.staticfiles.storage import staticfiles_storage

    return staticfiles_storage.url(path)


# Unfold admin theme
UNFOLD = {
    "SITE_TITLE": "Jheliz Admin",
    "SITE_HEADER": "Jheliz",
    "SITE_SUBHEADER": "Panel de administración",
    "SITE_SYMBOL": "storefront",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": "dark",
    "BORDER_RADIUS": "12px",
    # Cargamos los assets custom vía staticfiles_storage.url() para que
    # CompressedManifestStaticFilesStorage le añada el hash de contenido al
    # filename (ej. /static/admin/jheliz_polish.abc123.css). Sin el hash, los
    # browsers cachean cada archivo 1 año (max-age=31536000 que setea whitenoise)
    # y los usuarios nunca reciben fixes de CSS/JS. Con el hash, cada deploy
    # con cambios genera una URL nueva que el browser refetchea sí o sí.
    "STYLES": [
        lambda request: _hashed_static("admin/jheliz_polish.css"),
        lambda request: _hashed_static("admin/notifications_bell.css"),
        lambda request: _hashed_static("admin/users_redesign.css"),
        lambda request: _hashed_static("admin/changelist_polish.css"),
        # Capa "2026": sistema de diseño moderno (glass cards, pills, bento
        # stats, empty states ilustrados). Se carga al final para que sus
        # tokens y clases `.jh2-*` puedan sobrescribir reglas previas.
        lambda request: _hashed_static("admin/jheliz_2026.css"),
    ],
    "SCRIPTS": [
        lambda request: _hashed_static("admin/global_search.js"),
        lambda request: _hashed_static("admin/empty_state.js"),
        lambda request: _hashed_static("admin/ticket_templates.js"),
        lambda request: _hashed_static("admin/fab.js"),
        lambda request: _hashed_static("admin/toasts.js"),
        lambda request: _hashed_static("admin/keyboard_shortcuts.js"),
        lambda request: _hashed_static("admin/notifications_bell.js"),
    ],
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
        # Reagrupada por WORKFLOW del día a día (no por modelo Django).
        # Orden basado en frecuencia de uso real:
        # Inicio → Vender (catálogo) → Pedidos → Clientes → Marketing → Soporte → Sistema.
        "navigation": [
            {
                "title": "📊 Inicio",
                "separator": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "/panel-jheliz-2026/",
                    },
                    {
                        "title": "Reportes financieros",
                        "icon": "monitoring",
                        "link": "/panel-jheliz-2026/reports/",
                    },
                    {
                        "title": "Renovaciones",
                        "icon": "autorenew",
                        "link": "/panel-jheliz-2026/renewals/",
                    },
                    {
                        "title": "Estado de servicios",
                        "icon": "health_and_safety",
                        "link": "/panel-jheliz-2026/health/",
                    },
                    {
                        "title": "Ver tienda",
                        "icon": "public",
                        "link": "/",
                    },
                ],
            },
            {
                "title": "🛒 Vender",
                "separator": True,
                "items": [
                    {
                        "title": "Productos",
                        "icon": "inventory_2",
                        "link": "/panel-jheliz-2026/catalog/product/",
                    },
                    {
                        "title": "Planes — Cliente final",
                        "icon": "sell",
                        "link": "/panel-jheliz-2026/catalog/customerplan/",
                    },
                    {
                        "title": "Planes — Distribuidor",
                        "icon": "storefront",
                        "link": "/panel-jheliz-2026/catalog/distributorplan/",
                    },
                    {
                        "title": "Categorías",
                        "icon": "category",
                        "link": "/panel-jheliz-2026/catalog/category/",
                    },
                    {
                        "title": "Stock por producto",
                        "icon": "inventory",
                        "link": "/panel-jheliz-2026/stock/",
                    },
                    {
                        "title": "Stock (todos)",
                        "icon": "list_alt",
                        "link": "/panel-jheliz-2026/catalog/stockitem/",
                    },
                    {
                        "title": "Avísame cuando vuelva",
                        "icon": "notifications_active",
                        "link": "/panel-jheliz-2026/catalog/backinstockalert/",
                    },
                ],
            },
            {
                "title": "📦 Pedidos",
                "separator": True,
                "items": [
                    {
                        "title": "Pedidos clientes",
                        "icon": "receipt_long",
                        "link": "/panel-jheliz-2026/orders/order/",
                    },
                    {
                        "title": "Bandeja Yape",
                        "icon": "qr_code_scanner",
                        "link": "/panel-jheliz-2026/orders/order/yape-inbox/",
                    },
                    {
                        "title": "Items de pedidos",
                        "icon": "list_alt",
                        "link": "/panel-jheliz-2026/orders/orderitem/",
                    },
                    {
                        "title": "Pedidos mayoristas",
                        "icon": "local_shipping",
                        "link": "/panel-jheliz-2026/orders/distributororder/",
                    },
                    {
                        "title": "Reemplazar cuenta",
                        "icon": "sync_alt",
                        "link": "/panel-jheliz-2026/replace-blocked-account/",
                    },
                ],
            },
            {
                "title": "👥 Clientes",
                "separator": True,
                "items": [
                    {
                        "title": "Clientes",
                        "icon": "person",
                        "link": "/panel-jheliz-2026/accounts/customer/",
                    },
                    {
                        "title": "Clientes 360°",
                        "icon": "groups",
                        "link": "/panel-jheliz-2026/customers/",
                    },
                    {
                        "title": "Clientes valiosos",
                        "icon": "workspace_premium",
                        "link": "/panel-jheliz-2026/top-customers/",
                    },
                    {
                        "title": "Distribuidores",
                        "icon": "badge",
                        "link": "/panel-jheliz-2026/accounts/distributor/",
                    },
                    {
                        "title": "Movimientos de wallet",
                        "icon": "account_balance_wallet",
                        "link": "/panel-jheliz-2026/accounts/wallettransaction/",
                    },
                ],
            },
            {
                "title": "🎯 Marketing",
                "separator": True,
                "items": [
                    {
                        "title": "Cupones / códigos",
                        "icon": "redeem",
                        "link": "/panel-jheliz-2026/orders/coupon/",
                    },
                    {
                        "title": "Reseñas",
                        "icon": "reviews",
                        "link": "/panel-jheliz-2026/catalog/testimonial/",
                    },
                    {
                        "title": "Posts del blog",
                        "icon": "article",
                        "link": "/panel-jheliz-2026/blog/blogpost/",
                    },
                    {
                        "title": "Categorías de blog",
                        "icon": "label",
                        "link": "/panel-jheliz-2026/blog/blogcategory/",
                    },
                ],
            },
            {
                "title": "💬 Soporte",
                "separator": True,
                "items": [
                    {
                        "title": "Chats en vivo",
                        "icon": "chat",
                        "link": "/panel-jheliz-2026/livechat/",
                    },
                    {
                        "title": "Tickets",
                        "icon": "support_agent",
                        "link": "/panel-jheliz-2026/support/ticket/",
                    },
                    {
                        "title": "Solicitudes de código",
                        "icon": "mark_email_unread",
                        "link": "/panel-jheliz-2026/support/coderequest/",
                    },
                ],
            },
            {
                "title": "⚙️ Sistema",
                "separator": True,
                "items": [
                    {
                        "title": "Config. de pagos (Yape)",
                        "icon": "qr_code_2",
                        "link": "/panel-jheliz-2026/orders/paymentsettings/",
                    },
                    {
                        "title": "Usuarios (staff)",
                        "icon": "group",
                        "link": "/panel-jheliz-2026/accounts/user/",
                    },
                    {
                        "title": "2FA / autenticador",
                        "icon": "shield_lock",
                        "link": "/panel-jheliz-2026/security/2fa/",
                    },
                    {
                        "title": "Auditoría",
                        "icon": "fact_check",
                        "link": "/panel-jheliz-2026/auditoria/",
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
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=3, cast=int)
AXES_COOLOFF_TIME = config("AXES_COOLOFF_TIME_HOURS", default=24, cast=int)  # horas
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = None  # usa el formulario default con mensaje de error
AXES_VERBOSE = False

# Notificaciones (email + Telegram) cuando alguien inicia sesión en el admin.
# Útil para detectar rápido un acceso indebido — si recibes un correo de
# login y no fuiste tú, sabés que tu password se filtró.
ADMIN_LOGIN_NOTIFY = config("ADMIN_LOGIN_NOTIFY", default=True, cast=bool)

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
